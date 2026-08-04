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
    letter_count,
    letter_hint,
    name_matches,
)
from game.quests import EVENT_SILHOUETTE_FOUND, record_event
from silhouette.models import SilhouetteGame, SilhouetteGuess, SilhouettePlayer, SilhouetteRound

ROUND_SECONDS = 30
TYPE_HINT_AFTER = 5
LETTER_HINT_AFTER = 10
REVEAL_SECONDS = 5
MAX_POINTS = 1000
MIN_POINTS = 100
MAX_GUESS_LENGTH = 60


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
        raise StaleRevisionError("La partie a changé entre-temps.")


@transaction.atomic
def create_game(user, round_count: int) -> SilhouetteGame:
    if round_count not in SilhouetteGame.RoundCount.values:
        raise SilhouetteError("Nombre de manches invalide.")
    if _pokemon_pool().count() < 1:
        raise SilhouetteError("Le catalogue ne contient aucun Pokémon de la première génération.")

    game = SilhouetteGame.objects.create(created_by=user, round_count=round_count)
    SilhouettePlayer.objects.create(game=game, user=user)
    return game


@transaction.atomic
def join_game(game_id, user) -> SilhouetteGame:
    game = SilhouetteGame.objects.select_for_update().get(pk=game_id)
    if game.status != SilhouetteGame.Status.EN_ATTENTE:
        raise SilhouetteError("Cette partie a déjà commencé.")
    SilhouettePlayer.objects.get_or_create(game=game, user=user)
    _bump_revision(game)
    return game


@transaction.atomic
def start_game(game_id, user) -> SilhouetteGame:
    game = SilhouetteGame.objects.select_for_update().get(pk=game_id)
    if game.created_by_id != user.id:
        raise SilhouettePermissionError("Seul l'hôte peut lancer la partie.")
    if game.status != SilhouetteGame.Status.EN_ATTENTE:
        raise SilhouetteError("Cette partie a déjà commencé.")

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
        raise SilhouettePermissionError("Vous ne participez pas à cette partie.")
    _check_revision(game, expected_revision)

    if game.status != SilhouetteGame.Status.EN_COURS:
        raise SilhouetteError("La partie n'est pas en cours.")

    normalized_text = (text or "").strip()
    if not normalized_text:
        raise SilhouetteError("Écris un nom de Pokémon.")
    if len(normalized_text) > MAX_GUESS_LENGTH:
        raise SilhouetteError(f"Une proposition fait au plus {MAX_GUESS_LENGTH} caractères.")

    round_obj = current_round(game)
    if round_obj is None or round_obj.revealed_at is not None:
        raise SilhouetteError("Cette manche est terminée.")
    if round_obj.guesses.filter(player=player, is_correct=True).exists():
        raise SilhouetteError("Tu as déjà trouvé cette manche.")

    now = timezone.now()
    elapsed = (now - round_obj.started_at).total_seconds()
    if elapsed >= ROUND_SECONDS:
        raise SilhouetteError("Le temps de cette manche est écoulé.")

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
        hints["type"] = [pokemon_type.name_fr for pokemon_type in card.types]
    if revealed or elapsed >= LETTER_HINT_AFTER:
        hints["letters"] = letter_hint(card.name_fr)
        hints["letter_count"] = letter_count(card.name_fr)
    return hints


def serialize_game_state(game: SilhouetteGame, user) -> dict:
    player = game.players.filter(user=user).first()
    now = timezone.now()
    round_obj = current_round(game)

    players_payload = [
        {
            "id": entry.id,
            "username": entry.user.get_username(),
            "score": entry.score,
            "is_me": player is not None and entry.pk == player.pk,
        }
        for entry in game.players.select_related("user").all()
    ]

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
            "answer": round_obj.pokemon_card.name_fr if revealed else None,
            "hints": _hint_payload(round_obj, elapsed, revealed),
            "i_found": any(guess.player_id == getattr(player, "pk", None) for guess in found),
            "found": [
                {
                    "username": guess.player.user.get_username(),
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
        "status": game.status,
        "turn_revision": game.turn_revision,
        "round_count": game.round_count,
        "is_host": game.created_by_id == user.id,
        "is_player": player is not None,
        "players": players_payload,
        "round": round_payload,
    }


def get_lobby_state(user) -> dict:
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
                "is_mine": game.players.filter(user=user).exists(),
            }
            for game in open_games
        ]
    }
