import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from game.models import PokemonCard
from game.pokemon_names import active_language, bilingual_text, localized_pokemon_name
from game.quests import EVENT_GAME_PLAYED, EVENT_GAME_WON, record_event
from game.type_icons import type_icon_url

from .models import (
    GuessWhoCandidateState,
    GuessWhoGame,
    GuessWhoPlayer,
    GuessWhoRosterCard,
    GuessWhoTurn,
)

ROSTER_SIZE = 24
MAX_QUESTION_LENGTH = 500


class GuessWhoError(Exception):
    """Erreur métier sûre à afficher au joueur."""


class GuessWhoPermissionError(GuessWhoError):
    pass


class GuessWhoStateError(GuessWhoError):
    pass


class GuessWhoRosterError(GuessWhoError):
    pass


@dataclass(frozen=True)
class StaleRevisionError(GuessWhoError):
    expected: int
    actual: int

    def __str__(self):
        return bilingual_text(
            "L'état de la partie a changé. Il a été actualisé.",
            "The game state changed. It has been refreshed.",
        )


def _lock_game(game_id) -> GuessWhoGame:
    return GuessWhoGame.objects.select_for_update().get(pk=game_id)


def _get_player(game: GuessWhoGame, user) -> GuessWhoPlayer:
    player = game.players.select_related("user", "target_card").filter(user=user).first()
    if player is None:
        raise GuessWhoPermissionError(
            bilingual_text(
                "Vous ne participez pas à cette partie.",
                "You are not taking part in this game.",
            )
        )
    return player


def _assert_revision(game: GuessWhoGame, expected_revision: int):
    if expected_revision != game.turn_revision:
        raise StaleRevisionError(expected=expected_revision, actual=game.turn_revision)


def _increment_revision(game: GuessWhoGame, *update_fields: str):
    game.turn_revision += 1
    game.save(update_fields=[*update_fields, "turn_revision"])


def _get_pending_question(game: GuessWhoGame):
    return (
        game.turns.select_related("actor__user")
        .filter(kind=GuessWhoTurn.Kind.QUESTION, answer__isnull=True)
        .first()
    )


def _next_sequence(game: GuessWhoGame) -> int:
    latest = game.turns.aggregate(latest=Max("sequence"))["latest"]
    return (latest or 0) + 1


@transaction.atomic
def create_game(
    user,
    play_mode: str = GuessWhoGame.PlayMode.ONLINE,
) -> GuessWhoGame:
    """Crée une partie et tire au sort 24 cartes parmi tout le catalogue.

    Qui est-ce ? est un jeu d'identification pure (silhouette, nom, sprite) :
    contrairement à Poké-Uno, il ne dépend pas des types JCC ni du sous-
    ensemble ``in_current_deck`` réservé à ce mode. Le plateau est donc tiré
    au hasard à chaque partie, dans tout l'historique du catalogue, pour
    varier les parties tout en restant strictement identique pour les deux
    joueurs (une seule ligne de ``GuessWhoRosterCard`` par partie).
    """

    if play_mode not in GuessWhoGame.PlayMode.values:
        raise GuessWhoStateError(
            bilingual_text(
                "Choisis un mode de jeu valide.",
                "Choose a valid game mode.",
            )
        )

    pokemon_card_ids = list(PokemonCard.objects.values_list("pk", flat=True))
    if len(pokemon_card_ids) < ROSTER_SIZE:
        raise GuessWhoRosterError(
            bilingual_text(
                f"Le mode Qui est-ce ? nécessite au moins {ROSTER_SIZE} Pokémon au catalogue.",
                f"Guess Who? requires at least {ROSTER_SIZE} Pokémon in the catalogue.",
            )
        )

    selected_ids = random.sample(pokemon_card_ids, ROSTER_SIZE)
    cards_by_id = PokemonCard.objects.in_bulk(selected_ids)
    pokemon_cards = [cards_by_id[pk] for pk in selected_ids]

    game = GuessWhoGame.objects.create(created_by=user, play_mode=play_mode)
    GuessWhoPlayer.objects.create(game=game, user=user, turn_order=0)
    GuessWhoRosterCard.objects.bulk_create(
        [
            GuessWhoRosterCard(game=game, pokemon_card=card, position=position)
            for position, card in enumerate(pokemon_cards)
        ]
    )
    return game


@transaction.atomic
def join_game(game_id, user) -> tuple[GuessWhoGame, GuessWhoPlayer]:
    game = _lock_game(game_id)
    existing = game.players.filter(user=user).first()
    if existing is not None:
        return game, existing
    if game.status != GuessWhoGame.Status.EN_ATTENTE:
        raise GuessWhoStateError(
            bilingual_text(
                "Cette partie n'accepte plus de joueur.",
                "This game is no longer accepting players.",
            )
        )
    if game.players.count() >= 2:
        raise GuessWhoStateError(bilingual_text("Cette partie est complète.", "This game is full."))

    player = GuessWhoPlayer.objects.create(game=game, user=user, turn_order=1)
    game.status = GuessWhoGame.Status.CHOIX
    _increment_revision(game, "status")
    return game, player


@transaction.atomic
def choose_target(game_id, user, pokemon_card_id: int, expected_revision: int) -> GuessWhoGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != GuessWhoGame.Status.CHOIX:
        raise GuessWhoStateError(
            bilingual_text(
                "Le choix secret n'est pas disponible maintenant.",
                "Secret selection is not available right now.",
            )
        )
    if game.players.count() != 2:
        raise GuessWhoStateError(
            bilingual_text(
                "Deux joueurs sont nécessaires avant de choisir.",
                "Two players are required before choosing.",
            )
        )
    if player.target_card_id is not None:
        raise GuessWhoStateError(
            bilingual_text(
                "Ton Pokémon secret est déjà verrouillé.",
                "Your secret Pokémon is already locked.",
            )
        )

    roster_card = game.roster_cards.filter(pokemon_card_id=pokemon_card_id).first()
    if roster_card is None:
        raise GuessWhoRosterError(
            bilingual_text(
                "Ce Pokémon ne fait pas partie du plateau.",
                "This Pokémon is not on the board.",
            )
        )

    player.target_card = roster_card.pokemon_card
    player.save(update_fields=["target_card"])

    update_fields = []
    if not game.players.filter(target_card__isnull=True).exists():
        game.status = GuessWhoGame.Status.EN_COURS
        game.current_turn = game.players.get(turn_order=0)
        game.started_at = timezone.now()
        update_fields = ["status", "current_turn", "started_at"]
    _increment_revision(game, *update_fields)
    return game


@transaction.atomic
def ask_question(game_id, user, question: str | None, expected_revision: int) -> GuessWhoGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != GuessWhoGame.Status.EN_COURS:
        raise GuessWhoStateError(
            bilingual_text("La partie n'est pas en cours.", "The game is not in progress.")
        )
    if game.current_turn_id != player.id:
        raise GuessWhoStateError(bilingual_text("Ce n'est pas votre tour.", "It is not your turn."))
    if _get_pending_question(game) is not None:
        raise GuessWhoStateError(
            bilingual_text(
                "La question précédente attend encore une réponse.",
                "The previous question is still waiting for an answer.",
            )
        )
    # En IRL, la question reste strictement orale : même un client modifié
    # ne peut pas enregistrer le texte envoyé dans la requête.
    normalized_question = ""
    if game.play_mode == GuessWhoGame.PlayMode.ONLINE:
        if not isinstance(question, str):
            raise GuessWhoStateError(
                bilingual_text("La question doit être un texte.", "The question must be text.")
            )
        normalized_question = " ".join(question.split())
        if not normalized_question:
            raise GuessWhoStateError(
                bilingual_text("La question ne peut pas être vide.", "The question cannot be empty.")
            )
        if len(normalized_question) > MAX_QUESTION_LENGTH:
            raise GuessWhoStateError(
                bilingual_text(
                    f"La question ne peut pas dépasser {MAX_QUESTION_LENGTH} caractères.",
                    f"The question cannot exceed {MAX_QUESTION_LENGTH} characters.",
                )
            )

    GuessWhoTurn.objects.create(
        game=game,
        sequence=_next_sequence(game),
        kind=GuessWhoTurn.Kind.QUESTION,
        actor=player,
        question=normalized_question,
    )
    _increment_revision(game)
    return game


@transaction.atomic
def answer_question(game_id, user, answer: bool, expected_revision: int) -> GuessWhoGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != GuessWhoGame.Status.EN_COURS:
        raise GuessWhoStateError(
            bilingual_text("La partie n'est pas en cours.", "The game is not in progress.")
        )
    if not isinstance(answer, bool):
        raise GuessWhoStateError(
            bilingual_text("La réponse doit être Oui ou Non.", "The answer must be Yes or No.")
        )

    pending = _get_pending_question(game)
    if pending is None:
        raise GuessWhoStateError(
            bilingual_text(
                "Aucune question n'attend de réponse.",
                "No question is waiting for an answer.",
            )
        )
    if pending.actor_id == player.id:
        raise GuessWhoPermissionError(
            bilingual_text(
                "Vous ne pouvez pas répondre à votre propre question.",
                "You cannot answer your own question.",
            )
        )

    pending.answer = answer
    pending.responder = player
    pending.answered_at = timezone.now()
    pending.save(update_fields=["answer", "responder", "answered_at"])
    game.current_turn = player
    _increment_revision(game, "current_turn")
    return game


@transaction.atomic
def guess_pokemon(game_id, user, pokemon_card_id: int, expected_revision: int) -> GuessWhoGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != GuessWhoGame.Status.EN_COURS:
        raise GuessWhoStateError(
            bilingual_text("La partie n'est pas en cours.", "The game is not in progress.")
        )
    if game.current_turn_id != player.id:
        raise GuessWhoStateError(bilingual_text("Ce n'est pas votre tour.", "It is not your turn."))
    if _get_pending_question(game) is not None:
        raise GuessWhoStateError(
            bilingual_text(
                "La question en cours doit d'abord recevoir une réponse.",
                "The current question must be answered first.",
            )
        )

    roster_card = game.roster_cards.filter(pokemon_card_id=pokemon_card_id).first()
    if roster_card is None:
        raise GuessWhoRosterError(
            bilingual_text(
                "Ce Pokémon ne fait pas partie du plateau.",
                "This Pokémon is not on the board.",
            )
        )
    opponent = game.players.exclude(pk=player.pk).select_related("target_card").get()
    is_correct = opponent.target_card_id == roster_card.pokemon_card_id

    GuessWhoTurn.objects.create(
        game=game,
        sequence=_next_sequence(game),
        kind=GuessWhoTurn.Kind.GUESS,
        actor=player,
        guessed_card=roster_card.pokemon_card,
        is_correct=is_correct,
    )
    game.winner = player if is_correct else opponent
    game.status = GuessWhoGame.Status.TERMINEE
    game.finished_at = timezone.now()
    game.current_turn = None
    _increment_revision(game, "winner", "status", "finished_at", "current_turn")

    # Les deux joueurs ont joué une partie ; seul le gagnant marque la victoire.
    for participant in game.players.select_related("user"):
        record_event(participant.user, EVENT_GAME_PLAYED)
    record_event(game.winner.user, EVENT_GAME_WON)
    return game


@transaction.atomic
def toggle_candidate(
    game_id,
    user,
    pokemon_card_id: int,
    is_eliminated: bool,
    expected_revision: int,
) -> GuessWhoGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status == GuessWhoGame.Status.TERMINEE:
        raise GuessWhoStateError(bilingual_text("La partie est terminée.", "The game is over."))
    if not isinstance(is_eliminated, bool):
        raise GuessWhoStateError(bilingual_text("État de carte invalide.", "Invalid card state."))

    roster_card = game.roster_cards.filter(pokemon_card_id=pokemon_card_id).first()
    if roster_card is None:
        raise GuessWhoRosterError(
            bilingual_text(
                "Ce Pokémon ne fait pas partie du plateau.",
                "This Pokémon is not on the board.",
            )
        )
    GuessWhoCandidateState.objects.update_or_create(
        player=player,
        roster_card=roster_card,
        defaults={"is_eliminated": is_eliminated},
    )
    return game


@transaction.atomic
def reset_candidates(game_id, user, expected_revision: int) -> GuessWhoGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status == GuessWhoGame.Status.TERMINEE:
        raise GuessWhoStateError(bilingual_text("La partie est terminée.", "The game is over."))

    GuessWhoCandidateState.objects.filter(
        player=player,
        is_eliminated=True,
    ).update(
        is_eliminated=False,
        updated_at=timezone.now(),
    )
    return game


def _serialize_card(pokemon_card: PokemonCard) -> dict:
    return {
        "id": pokemon_card.id,
        "pokedex_id": pokemon_card.pokedex_id,
        "name": localized_pokemon_name(pokemon_card),
        "name_fr": pokemon_card.name_fr,
        "name_en": pokemon_card.name_en,
        "sprite_url": pokemon_card.sprite_url,
        "primary_type": pokemon_card.primary_type.slug,
        "type_icon_url": type_icon_url(pokemon_card.primary_type.slug),
        "secondary_type": pokemon_card.secondary_type.slug if pokemon_card.secondary_type else None,
    }


def _serialize_player_brief(player: GuessWhoPlayer | None):
    if player is None:
        return None
    return {
        "id": player.id,
        "username": player.user.get_username(),
        "turn_order": player.turn_order,
    }


def serialize_game_state(game: GuessWhoGame, user) -> dict:
    """Sérialise un état personnalisé sans jamais divulguer le secret adverse."""

    players = list(
        game.players.select_related(
            "user",
            "target_card__primary_type",
            "target_card__secondary_type",
        ).order_by("turn_order")
    )
    me = next((player for player in players if player.user_id == user.id), None)
    if me is None:
        raise GuessWhoPermissionError(
            bilingual_text(
                "Vous ne participez pas à cette partie.",
                "You are not taking part in this game.",
            )
        )

    roster = list(
        game.roster_cards.select_related(
            "pokemon_card__primary_type",
            "pokemon_card__secondary_type",
        ).order_by("position")
    )
    eliminated_by_roster_id = dict(
        GuessWhoCandidateState.objects.filter(player=me).values_list("roster_card_id", "is_eliminated")
    )

    pending = _get_pending_question(game)
    players_payload = []
    reveal_all_targets = game.status == GuessWhoGame.Status.TERMINEE
    for player in players:
        may_see_target = reveal_all_targets or player.id == me.id
        players_payload.append(
            {
                **_serialize_player_brief(player),
                "has_chosen": player.target_card_id is not None,
                "target": (
                    _serialize_card(player.target_card)
                    if may_see_target and player.target_card is not None
                    else None
                ),
            }
        )

    history = []
    turns = game.turns.select_related(
        "actor__user",
        "responder__user",
        "guessed_card__primary_type",
        "guessed_card__secondary_type",
    )
    for turn in turns:
        entry = {
            "id": turn.id,
            "sequence": turn.sequence,
            "kind": turn.kind,
            "actor": _serialize_player_brief(turn.actor),
            "question": turn.question if turn.kind == GuessWhoTurn.Kind.QUESTION else None,
            "answer": turn.answer,
            "responder": _serialize_player_brief(turn.responder),
            "guessed_card": (_serialize_card(turn.guessed_card) if turn.guessed_card is not None else None),
            "is_correct": turn.is_correct,
            "created_at": turn.created_at.isoformat(),
            "answered_at": turn.answered_at.isoformat() if turn.answered_at else None,
        }
        history.append(entry)

    current_turn = next(
        (player for player in players if player.id == game.current_turn_id),
        None,
    )
    can_answer = (
        game.status == GuessWhoGame.Status.EN_COURS and pending is not None and pending.actor_id != me.id
    )
    is_my_turn = (
        game.status == GuessWhoGame.Status.EN_COURS and pending is None and game.current_turn_id == me.id
    )
    return {
        "game_id": str(game.id),
        "language": active_language(),
        "play_mode": game.play_mode,
        "status": game.status,
        "turn_revision": game.turn_revision,
        "is_creator": game.created_by_id == user.id,
        "is_my_turn": is_my_turn,
        "can_answer": can_answer,
        "can_choose_target": (game.status == GuessWhoGame.Status.CHOIX and me.target_card_id is None),
        "current_turn": _serialize_player_brief(current_turn),
        "winner": _serialize_player_brief(
            next((player for player in players if player.id == game.winner_id), None)
        ),
        "me": next(player for player in players_payload if player["id"] == me.id),
        "players": players_payload,
        "roster": [
            {
                **_serialize_card(roster_card.pokemon_card),
                "position": roster_card.position,
                "is_eliminated": eliminated_by_roster_id.get(roster_card.id, False),
            }
            for roster_card in roster
        ],
        "pending_question": (
            {
                "id": pending.id,
                "actor": _serialize_player_brief(pending.actor),
                "question": pending.question,
            }
            if pending is not None
            else None
        ),
        "history": history,
    }


def get_lobby_state(user) -> dict:
    open_games = (
        GuessWhoGame.objects.filter(status=GuessWhoGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .prefetch_related("players__user")
        .order_by("-created_at")
    )
    my_games = []
    if getattr(user, "is_authenticated", False):
        my_games = list(
            GuessWhoGame.objects.annotate(player_count=Count("players"))
            .filter(players__user=user)
            .order_by("-created_at")
        )
    return {
        "language": active_language(),
        "open_games": [
            {
                "id": str(game.id),
                "creator": game.created_by.get_username(),
                "player_count": len(game.players.all()),
                "max_players": 2,
                "status": game.status,
                "play_mode": game.play_mode,
            }
            for game in open_games
        ],
        "my_games": [
            {
                "id": str(game.id),
                "status": game.status,
                "player_count": game.player_count,
                "winner_id": game.winner_id,
                "play_mode": game.play_mode,
            }
            for game in my_games
        ],
        "my_game_ids": [str(game.id) for game in my_games],
    }
