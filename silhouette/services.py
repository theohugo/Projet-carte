"""Règles de « Qui est ce Pokémon ? », isolées des vues.

Le serveur est seul maître de l'horloge : les indices, le score et la fin d'une
manche se déduisent de ``SilhouetteRound.started_at``, jamais d'un compteur
envoyé par le navigateur. La réponse n'est transmise au client qu'une fois la
manche révélée, et l'illustration passe par un proxy qui masque le Pokédex ID.
"""

import random

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from game.models import PokemonCard
from game.pokemon_names import (
    GEN_ONE_MAX_POKEDEX_ID,
    active_language,
    bilingual_text,
    letter_count,
    letter_hint,
    localized_pokemon_name,
    localized_type_name,
    name_matches,
)
from game.quests import EVENT_SILHOUETTE_FOUND, record_event
from game.type_icons import type_icon_url
from silhouette.models import SilhouetteGame, SilhouetteGuess, SilhouettePlayer, SilhouetteRound

ROUND_SECONDS = 30
TYPE_HINT_AFTER = 5
LETTER_HINT_AFTER = 10
REVEAL_SECONDS = 5
MAX_POINTS = 1000
MIN_POINTS = 100
MAX_GUESS_LENGTH = 60
MAX_BOTS = 5
BOT_NAMES = ("IA Zorua", "IA Motisma", "IA Porygon", "IA Métamorph", "IA Mew")
BOT_MIN_CORRECT_DELAY = 8
BOT_CORRECT_DELAY_SPAN = 13


class SilhouetteError(Exception):
    """Erreur métier du mode silhouette."""


class SilhouettePermissionError(SilhouetteError):
    pass


class StaleRevisionError(SilhouetteError):
    pass


def _pokemon_pool():
    return PokemonCard.objects.filter(pokedex_id__lte=GEN_ONE_MAX_POKEDEX_ID)


def points_for(elapsed_seconds: float) -> int:
    """Score d'une bonne réponse : plus c'est rapide, plus ça rapporte."""

    remaining = max(0.0, ROUND_SECONDS - max(0.0, elapsed_seconds))
    return max(MIN_POINTS, round(MAX_POINTS * remaining / ROUND_SECONDS))


def _bump_revision(game: SilhouetteGame):
    game.turn_revision += 1
    game.save(update_fields=["turn_revision"])


def _check_revision(game: SilhouetteGame, expected_revision):
    if expected_revision is not None and expected_revision != game.turn_revision:
        raise StaleRevisionError(
            bilingual_text("La partie a changé entre-temps.", "The game changed in the meantime.")
        )


@transaction.atomic
def create_game(user, round_count: int) -> SilhouetteGame:
    if round_count not in SilhouetteGame.RoundCount.values:
        raise SilhouetteError(bilingual_text("Nombre de manches invalide.", "Invalid number of rounds."))
    if _pokemon_pool().count() < 1:
        raise SilhouetteError(
            bilingual_text(
                "Le catalogue ne contient aucun Pokémon de la première génération.",
                "The catalogue does not contain any first-generation Pokémon.",
            )
        )

    game = SilhouetteGame.objects.create(created_by=user, round_count=round_count)
    SilhouettePlayer.objects.create(game=game, user=user)
    return game


@transaction.atomic
def join_game(game_id, user) -> SilhouetteGame:
    game = SilhouetteGame.objects.select_for_update().get(pk=game_id)
    if game.status != SilhouetteGame.Status.EN_ATTENTE:
        raise SilhouetteError(
            bilingual_text("Cette partie a déjà commencé.", "This game has already started.")
        )
    SilhouettePlayer.objects.get_or_create(game=game, user=user)
    _bump_revision(game)
    return game


@transaction.atomic
def add_bot(game_id, user) -> SilhouettePlayer:
    """Add one server-controlled opponent while the room is waiting."""

    game = SilhouetteGame.objects.select_for_update().get(pk=game_id)
    if game.created_by_id != user.id:
        raise SilhouettePermissionError(
            bilingual_text("Seul l'hôte peut ajouter une IA.", "Only the host can add an AI.")
        )
    if game.status != SilhouetteGame.Status.EN_ATTENTE:
        raise SilhouetteError(
            bilingual_text(
                "Impossible d'ajouter une IA après le lancement.",
                "An AI cannot be added after the game starts.",
            )
        )
    used_names = set(game.players.filter(user__isnull=True).values_list("bot_name", flat=True))
    available_name = next((name for name in BOT_NAMES if name not in used_names), None)
    if available_name is None or len(used_names) >= MAX_BOTS:
        raise SilhouetteError(
            bilingual_text(
                f"Un salon accepte au plus {MAX_BOTS} IA.",
                f"A room allows at most {MAX_BOTS} AIs.",
            )
        )
    player = SilhouettePlayer.objects.create(game=game, bot_name=available_name)
    _bump_revision(game)
    return player


@transaction.atomic
def remove_bot(game_id, user, player_id: int) -> SilhouetteGame:
    """Remove a bot; human participants can never be targeted by this action."""

    game = SilhouetteGame.objects.select_for_update().get(pk=game_id)
    if game.created_by_id != user.id:
        raise SilhouettePermissionError(
            bilingual_text("Seul l'hôte peut retirer une IA.", "Only the host can remove an AI.")
        )
    if game.status != SilhouetteGame.Status.EN_ATTENTE:
        raise SilhouetteError(
            bilingual_text(
                "Impossible de retirer une IA après le lancement.",
                "An AI cannot be removed after the game starts.",
            )
        )
    bot = game.players.filter(pk=player_id, user__isnull=True).first()
    if bot is None:
        raise SilhouetteError(bilingual_text("Cette IA n'existe plus.", "This AI no longer exists."))
    bot.delete()
    _bump_revision(game)
    return game


@transaction.atomic
def start_game(game_id, user) -> SilhouetteGame:
    game = SilhouetteGame.objects.select_for_update().get(pk=game_id)
    if game.created_by_id != user.id:
        raise SilhouettePermissionError(
            bilingual_text("Seul l'hôte peut lancer la partie.", "Only the host can start the game.")
        )
    if game.status != SilhouetteGame.Status.EN_ATTENTE:
        raise SilhouetteError(
            bilingual_text("Cette partie a déjà commencé.", "This game has already started.")
        )

    game.status = SilhouetteGame.Status.EN_COURS
    game.started_at = timezone.now()
    game.save(update_fields=["status", "started_at"])
    _open_round(game, number=1)
    _bump_revision(game)
    return game


def _open_round(game: SilhouetteGame, number: int) -> SilhouetteRound:
    """Tire une espèce jamais vue dans cette partie et démarre son chronomètre."""

    already_used = game.rounds.values_list("pokemon_card_id", flat=True)
    pool = list(_pokemon_pool().exclude(pk__in=already_used).values_list("pk", flat=True))
    if not pool:
        # Partie plus longue que le catalogue : on autorise les répétitions
        # plutôt que d'interrompre la partie.
        pool = list(_pokemon_pool().values_list("pk", flat=True))

    return SilhouetteRound.objects.create(
        game=game,
        number=number,
        pokemon_card_id=random.choice(pool),
        started_at=timezone.now(),
    )


def current_round(game: SilhouetteGame) -> SilhouetteRound | None:
    return game.rounds.select_related("pokemon_card__primary_type", "pokemon_card__secondary_type").last()


def _round_is_over(game: SilhouetteGame, round_obj: SilhouetteRound, now) -> bool:
    """Une manche s'arrête au temps écoulé ou quand tout le monde a trouvé."""

    if (now - round_obj.started_at).total_seconds() >= ROUND_SECONDS:
        return True
    player_count = game.players.count()
    found = round_obj.guesses.filter(is_correct=True).count()
    return player_count > 0 and found >= player_count


def _bot_delays(round_obj: SilhouetteRound, player: SilhouettePlayer) -> tuple[int, int]:
    """Stable, non-secret timings so repeated polls cannot reroll a bot."""

    seed = (round_obj.pk * 37) + (player.pk * 17)
    correct_after = BOT_MIN_CORRECT_DELAY + (seed % BOT_CORRECT_DELAY_SPAN)
    wrong_after = max(4, correct_after - 4 - (seed % 3))
    return wrong_after, correct_after


def _bot_decoy(round_obj: SilhouetteRound, player: SilhouettePlayer):
    candidates = list(
        _pokemon_pool()
        .exclude(pk=round_obj.pokemon_card_id)
        .order_by("pokedex_id")
        .values_list("name_fr", flat=True)
    )
    if not candidates:
        return None
    return candidates[(round_obj.pk + player.pk) % len(candidates)]


def _play_bot_guesses(game: SilhouetteGame, round_obj: SilhouetteRound, now) -> bool:
    """Materialise due bot guesses during normal polling, never client-side.

    A bot first submits at most one real catalogue name as a plausible decoy,
    then its correct answer after a stable 8–20 second delay.  Neither answer
    is serialized before the normal reveal; only the public "found" marker is.
    """

    elapsed = (now - round_obj.started_at).total_seconds()
    if elapsed < 0 or round_obj.revealed_at is not None:
        return False

    changed = False
    for bot in game.players.filter(user__isnull=True).order_by("pk"):
        guesses = round_obj.guesses.filter(player=bot)
        if guesses.filter(is_correct=True).exists():
            continue
        wrong_after, correct_after = _bot_delays(round_obj, bot)
        if elapsed >= correct_after:
            points = points_for(elapsed)
            SilhouetteGuess.objects.create(
                round=round_obj,
                player=bot,
                text=round_obj.pokemon_card.name_fr,
                is_correct=True,
                elapsed_ms=max(0, int(elapsed * 1000)),
                points=points,
            )
            bot.score += points
            bot.save(update_fields=["score"])
            changed = True
        elif elapsed >= wrong_after and not guesses.exists():
            decoy = _bot_decoy(round_obj, bot)
            if decoy:
                SilhouetteGuess.objects.create(
                    round=round_obj,
                    player=bot,
                    text=decoy,
                    is_correct=False,
                    elapsed_ms=max(0, int(elapsed * 1000)),
                )
                changed = True
    if changed:
        _bump_revision(game)
    return changed


@transaction.atomic
def advance_if_needed(game_id) -> SilhouetteGame:
    """Fait avancer l'horloge de la partie : révélation puis manche suivante.

    Appelée par n'importe quel client au fil de son polling : la transaction et
    le verrou garantissent qu'une manche n'est ouverte qu'une fois, quel que
    soit le nombre de joueurs qui interrogent l'API au même instant.
    """

    game = SilhouetteGame.objects.select_for_update().get(pk=game_id)
    if game.status != SilhouetteGame.Status.EN_COURS:
        return game

    now = timezone.now()
    round_obj = current_round(game)
    if round_obj is None:
        _open_round(game, number=1)
        _bump_revision(game)
        return game

    if round_obj.revealed_at is None:
        _play_bot_guesses(game, round_obj, now)
        if not _round_is_over(game, round_obj, now):
            return game
        round_obj.revealed_at = now
        round_obj.save(update_fields=["revealed_at"])
        _bump_revision(game)
        return game

    if (now - round_obj.revealed_at).total_seconds() < REVEAL_SECONDS:
        return game

    if round_obj.number >= game.round_count:
        game.status = SilhouetteGame.Status.TERMINEE
        game.finished_at = now
        game.save(update_fields=["status", "finished_at"])
    else:
        _open_round(game, number=round_obj.number + 1)
    _bump_revision(game)
    return game


@transaction.atomic
def submit_guess(game_id, user, text: str, expected_revision=None) -> dict:
    game = SilhouetteGame.objects.select_for_update().get(pk=game_id)
    player = game.players.filter(user=user).first()
    if player is None:
        raise SilhouettePermissionError(
            bilingual_text("Vous ne participez pas à cette partie.", "You are not in this game.")
        )
    _check_revision(game, expected_revision)

    if game.status != SilhouetteGame.Status.EN_COURS:
        raise SilhouetteError(bilingual_text("La partie n'est pas en cours.", "The game is not in progress."))

    normalized_text = (text or "").strip()
    if not normalized_text:
        raise SilhouetteError(bilingual_text("Écris un nom de Pokémon.", "Enter a Pokémon name."))
    if len(normalized_text) > MAX_GUESS_LENGTH:
        raise SilhouetteError(
            bilingual_text(
                f"Une proposition fait au plus {MAX_GUESS_LENGTH} caractères.",
                f"A guess can contain at most {MAX_GUESS_LENGTH} characters.",
            )
        )

    round_obj = current_round(game)
    if round_obj is None or round_obj.revealed_at is not None:
        raise SilhouetteError(bilingual_text("Cette manche est terminée.", "This round is over."))
    if round_obj.guesses.filter(player=player, is_correct=True).exists():
        raise SilhouetteError(
            bilingual_text("Tu as déjà trouvé cette manche.", "You have already solved this round.")
        )

    now = timezone.now()
    elapsed = (now - round_obj.started_at).total_seconds()
    if elapsed >= ROUND_SECONDS:
        raise SilhouetteError(
            bilingual_text("Le temps de cette manche est écoulé.", "Time is up for this round.")
        )

    is_correct = name_matches(normalized_text, round_obj.pokemon_card)
    points = points_for(elapsed) if is_correct else 0
    SilhouetteGuess.objects.create(
        round=round_obj,
        player=player,
        text=normalized_text[:MAX_GUESS_LENGTH],
        is_correct=is_correct,
        elapsed_ms=int(elapsed * 1000),
        points=points,
    )

    if is_correct:
        player.score += points
        player.save(update_fields=["score"])
        record_event(player.user, EVENT_SILHOUETTE_FOUND)
        if _round_is_over(game, round_obj, now):
            round_obj.revealed_at = now
            round_obj.save(update_fields=["revealed_at"])
    _bump_revision(game)

    return {"is_correct": is_correct, "points": points}


def _hint_payload(round_obj: SilhouetteRound, elapsed: float, revealed: bool) -> dict:
    """Indices débloqués par le temps. Rien n'est envoyé avant son heure."""

    card = round_obj.pokemon_card
    hints = {"type": None, "letters": None, "letter_count": None}
    if revealed or elapsed >= TYPE_HINT_AFTER:
        hints["type"] = [
            {
                "slug": pokemon_type.slug,
                "name": localized_type_name(pokemon_type),
                "name_fr": pokemon_type.name_fr,
                "name_en": pokemon_type.name_en,
                "icon_url": type_icon_url(pokemon_type.slug),
            }
            for pokemon_type in card.types
        ]
    if revealed or elapsed >= LETTER_HINT_AFTER:
        name = localized_pokemon_name(card)
        hints["letters"] = letter_hint(name)
        hints["letter_count"] = letter_count(name)
    return hints


def serialize_game_state(game: SilhouetteGame, user) -> dict:
    player = game.players.filter(user=user).first()
    now = timezone.now()
    round_obj = current_round(game)

    players_payload = [
        {
            "id": entry.id,
            "username": entry.display_name,
            "score": entry.score,
            "is_bot": entry.is_bot,
            "is_me": player is not None and entry.pk == player.pk,
        }
        for entry in game.players.select_related("user").all()
    ]
    bot_count = sum(1 for entry in players_payload if entry["is_bot"])

    round_payload = None
    if round_obj is not None:
        revealed = round_obj.revealed_at is not None
        elapsed = (now - round_obj.started_at).total_seconds()
        found = list(
            round_obj.guesses.filter(is_correct=True).select_related("player__user").order_by("elapsed_ms")
        )
        my_guesses = list(round_obj.guesses.filter(player=player).order_by("created_at")) if player else []
        round_payload = {
            "number": round_obj.number,
            "total": game.round_count,
            "image_url": f"/qui-est-ce-pokemon/rounds/{round_obj.id}/image/",
            "seconds_left": max(0, round(ROUND_SECONDS - elapsed)) if not revealed else 0,
            "round_seconds": ROUND_SECONDS,
            "revealed": revealed,
            "answer": localized_pokemon_name(round_obj.pokemon_card) if revealed else None,
            "hints": _hint_payload(round_obj, elapsed, revealed),
            "i_found": any(guess.player_id == getattr(player, "pk", None) for guess in found),
            "found": [
                {
                    "username": guess.player.display_name,
                    "seconds": round(guess.elapsed_ms / 1000, 1),
                    "points": guess.points,
                }
                for guess in found
            ],
            # Les mauvaises propositions ne sont visibles que par leur auteur :
            # sinon la table entière élimine les réponses sans rien deviner.
            "my_guesses": [
                {"text": guess.text, "is_correct": guess.is_correct, "points": guess.points}
                for guess in my_guesses
            ],
        }

    return {
        "game_id": str(game.id),
        "language": active_language(),
        "status": game.status,
        "turn_revision": game.turn_revision,
        "round_count": game.round_count,
        "is_host": game.created_by_id == user.id,
        "bot_count": bot_count,
        "max_bots": MAX_BOTS,
        "can_add_bot": (
            game.created_by_id == user.id
            and game.status == SilhouetteGame.Status.EN_ATTENTE
            and bot_count < MAX_BOTS
        ),
        "is_player": player is not None,
        "players": players_payload,
        "round": round_payload,
    }


def get_lobby_state(user) -> dict:
    is_authenticated = getattr(user, "is_authenticated", False)
    open_games = (
        SilhouetteGame.objects.filter(status=SilhouetteGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
    )
    return {
        "open_games": [
            {
                "id": str(game.id),
                "host": game.created_by.get_username(),
                "player_count": game.player_count,
                "round_count": game.round_count,
                "is_mine": is_authenticated and game.players.filter(user=user).exists(),
            }
            for game in open_games
        ]
    }
