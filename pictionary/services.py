"""Règles du Pictionary Pokémon, isolées des vues.

Le dessinateur est le seul à recevoir le nom à faire deviner ; les autres ne
reçoivent que les traits déjà tracés. Les traits sont transmis par curseur
incrémental (``sequence``) : chaque client ne redemande que ce qu'il n'a pas.
"""

import random

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from game.models import PokemonCard
from game.pokemon_names import GEN_ONE_MAX_POKEDEX_ID, name_matches
from game.quests import EVENT_PICTIONARY_DRAWN, EVENT_PICTIONARY_FOUND, record_event
from pictionary.models import (
    PictionaryGame,
    PictionaryGuess,
    PictionaryPlayer,
    PictionaryRound,
    PictionaryStroke,
)

ROUND_SECONDS = 90
REVEAL_SECONDS = 6
MAX_POINTS = 600
MIN_POINTS = 100
DRAWER_POINTS_PER_FINDER = 150
MAX_GUESS_LENGTH = 60
MAX_POINTS_PER_STROKE = 400
MIN_PLAYERS = 2


class PictionaryError(Exception):
    """Erreur métier du Pictionary."""


class PictionaryPermissionError(PictionaryError):
    pass


class StaleRevisionError(PictionaryError):
    pass


def _pokemon_pool():
    return PokemonCard.objects.filter(pokedex_id__lte=GEN_ONE_MAX_POKEDEX_ID)


def points_for(elapsed_seconds: float) -> int:
    """Score d'un devineur : décroît avec le temps passé sur la manche."""

    remaining = max(0.0, ROUND_SECONDS - max(0.0, elapsed_seconds))
    return max(MIN_POINTS, round(MAX_POINTS * remaining / ROUND_SECONDS))


def _bump_revision(game: PictionaryGame):
    game.turn_revision += 1
    game.save(update_fields=["turn_revision"])


@transaction.atomic
def create_game(user, round_count: int) -> PictionaryGame:
    if round_count not in PictionaryGame.RoundCount.values:
        raise PictionaryError("Nombre de manches invalide.")
    game = PictionaryGame.objects.create(created_by=user, round_count=round_count)
    PictionaryPlayer.objects.create(game=game, user=user, turn_order=0)
    return game


@transaction.atomic
def join_game(game_id, user) -> PictionaryGame:
    game = PictionaryGame.objects.select_for_update().get(pk=game_id)
    if game.status != PictionaryGame.Status.EN_ATTENTE:
        raise PictionaryError("Cette partie a déjà commencé.")
    if not game.players.filter(user=user).exists():
        PictionaryPlayer.objects.create(game=game, user=user, turn_order=game.players.count())
    _bump_revision(game)
    return game


@transaction.atomic
def start_game(game_id, user) -> PictionaryGame:
    game = PictionaryGame.objects.select_for_update().get(pk=game_id)
    if game.created_by_id != user.id:
        raise PictionaryPermissionError("Seul l'hôte peut lancer la partie.")
    if game.status != PictionaryGame.Status.EN_ATTENTE:
        raise PictionaryError("Cette partie a déjà commencé.")
    if game.players.count() < MIN_PLAYERS:
        raise PictionaryError(f"Il faut au moins {MIN_PLAYERS} joueurs : un dessine, les autres devinent.")

    game.status = PictionaryGame.Status.EN_COURS
    game.started_at = timezone.now()
    game.save(update_fields=["status", "started_at"])
    _open_round(game, number=1)
    _bump_revision(game)
    return game


def _open_round(game: PictionaryGame, number: int) -> PictionaryRound:
    """Ouvre une manche : le dessinateur tourne, l'espèce n'est jamais reprise."""

    players = list(game.players.order_by("turn_order"))
    drawer = players[(number - 1) % len(players)]

    already_used = game.rounds.values_list("pokemon_card_id", flat=True)
    pool = list(_pokemon_pool().exclude(pk__in=already_used).values_list("pk", flat=True))
    if not pool:
        pool = list(_pokemon_pool().values_list("pk", flat=True))
    if not pool:
        raise PictionaryError("Le catalogue ne contient aucun Pokémon de la première génération.")

    return PictionaryRound.objects.create(
        game=game,
        number=number,
        drawer=drawer,
        pokemon_card_id=random.choice(pool),
        started_at=timezone.now(),
    )


def current_round(game: PictionaryGame) -> PictionaryRound | None:
    return game.rounds.select_related("pokemon_card", "drawer__user").last()


def _round_is_over(game: PictionaryGame, round_obj: PictionaryRound, now) -> bool:
    if (now - round_obj.started_at).total_seconds() >= ROUND_SECONDS:
        return True
    guesser_count = game.players.exclude(pk=round_obj.drawer_id).count()
    found = round_obj.guesses.filter(is_correct=True).count()
    return guesser_count > 0 and found >= guesser_count


@transaction.atomic
def advance_if_needed(game_id) -> PictionaryGame:
    """Termine la manche en cours puis ouvre la suivante, de façon idempotente."""

    game = PictionaryGame.objects.select_for_update().get(pk=game_id)
    if game.status != PictionaryGame.Status.EN_COURS:
        return game

    now = timezone.now()
    round_obj = current_round(game)
    if round_obj is None:
        _open_round(game, number=1)
        _bump_revision(game)
        return game

    if round_obj.ended_at is None:
        if not _round_is_over(game, round_obj, now):
            return game
        round_obj.ended_at = now
        round_obj.save(update_fields=["ended_at"])
        _bump_revision(game)
        return game

    if (now - round_obj.ended_at).total_seconds() < REVEAL_SECONDS:
        return game

    if round_obj.number >= game.round_count:
        game.status = PictionaryGame.Status.TERMINEE
        game.finished_at = now
        game.save(update_fields=["status", "finished_at"])
    else:
        _open_round(game, number=round_obj.number + 1)
    _bump_revision(game)
    return game


def _active_round_for(game: PictionaryGame) -> PictionaryRound:
    round_obj = current_round(game)
    if round_obj is None or round_obj.ended_at is not None:
        raise PictionaryError("Cette manche est terminée.")
    return round_obj


@transaction.atomic
def add_stroke(game_id, user, stroke: dict) -> int:
    """Enregistre un trait du dessinateur et renvoie son numéro de séquence."""

    game = PictionaryGame.objects.select_for_update().get(pk=game_id)
    player = game.players.filter(user=user).first()
    if player is None:
        raise PictionaryPermissionError("Vous ne participez pas à cette partie.")
    if game.status != PictionaryGame.Status.EN_COURS:
        raise PictionaryError("La partie n'est pas en cours.")

    round_obj = _active_round_for(game)
    if round_obj.drawer_id != player.pk:
        raise PictionaryPermissionError("Seul le dessinateur peut dessiner.")

    is_clear = bool(stroke.get("is_clear"))
    points = [] if is_clear else _clean_points(stroke.get("points"))
    if not is_clear and len(points) < 1:
        raise PictionaryError("Trait vide.")

    next_sequence = (round_obj.strokes.aggregate(top=Max("sequence"))["top"] or 0) + 1
    PictionaryStroke.objects.create(
        round=round_obj,
        sequence=next_sequence,
        points=points,
        color=_clean_color(stroke.get("color")),
        width=_clean_width(stroke.get("width")),
        is_clear=is_clear,
    )
    return next_sequence


def _clean_points(raw_points):
    """Ne garde que des coordonnées normalisées entre 0 et 1, arrondies."""

    if not isinstance(raw_points, list):
        return []
    cleaned = []
    for point in raw_points[:MAX_POINTS_PER_STROKE]:
        if not isinstance(point, list | tuple) or len(point) != 2:
            continue
        x, y = point
        if not isinstance(x, int | float) or not isinstance(y, int | float):
            continue
        if isinstance(x, bool) or isinstance(y, bool):
            continue
        cleaned.append([round(min(1.0, max(0.0, float(x))), 4), round(min(1.0, max(0.0, float(y))), 4)])
    return cleaned


def _clean_color(raw_color):
    is_hex_color = (
        isinstance(raw_color, str)
        and len(raw_color) == 7
        and raw_color.startswith("#")
        and all(char in "0123456789abcdefABCDEF" for char in raw_color[1:])
    )
    return raw_color if is_hex_color else "#f6f9ff"


def _clean_width(raw_width):
    if isinstance(raw_width, bool) or not isinstance(raw_width, int):
        return 4
    return max(2, min(24, raw_width))


@transaction.atomic
def submit_guess(game_id, user, text: str, expected_revision=None) -> dict:
    game = PictionaryGame.objects.select_for_update().get(pk=game_id)
    player = game.players.filter(user=user).first()
    if player is None:
        raise PictionaryPermissionError("Vous ne participez pas à cette partie.")
    if expected_revision is not None and expected_revision != game.turn_revision:
        raise StaleRevisionError("La partie a changé entre-temps.")
    if game.status != PictionaryGame.Status.EN_COURS:
        raise PictionaryError("La partie n'est pas en cours.")

    round_obj = _active_round_for(game)
    if round_obj.drawer_id == player.pk:
        raise PictionaryError("Le dessinateur ne peut pas proposer de réponse.")
    if round_obj.guesses.filter(player=player, is_correct=True).exists():
        raise PictionaryError("Tu as déjà trouvé cette manche.")

    normalized_text = (text or "").strip()
    if not normalized_text:
        raise PictionaryError("Écris un nom de Pokémon.")
    if len(normalized_text) > MAX_GUESS_LENGTH:
        raise PictionaryError(f"Une proposition fait au plus {MAX_GUESS_LENGTH} caractères.")

    now = timezone.now()
    elapsed = (now - round_obj.started_at).total_seconds()
    is_correct = name_matches(normalized_text, round_obj.pokemon_card)
    points = points_for(elapsed) if is_correct else 0

    PictionaryGuess.objects.create(
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
        # Le dessinateur marque à chaque joueur qui trouve : son intérêt est
        # de dessiner vite et clair, pas de bloquer la manche.
        drawer = round_obj.drawer
        drawer.score += DRAWER_POINTS_PER_FINDER
        drawer.save(update_fields=["score"])
        record_event(player.user, EVENT_PICTIONARY_FOUND)
        record_event(drawer.user, EVENT_PICTIONARY_DRAWN)
        if _round_is_over(game, round_obj, now):
            round_obj.ended_at = now
            round_obj.save(update_fields=["ended_at"])
    _bump_revision(game)

    return {"is_correct": is_correct, "points": points}


def serialize_game_state(game: PictionaryGame, user, *, since_sequence: int = 0) -> dict:
    player = game.players.filter(user=user).first()
    now = timezone.now()
    round_obj = current_round(game)

    players_payload = [
        {
            "id": entry.id,
            "username": entry.user.get_username(),
            "score": entry.score,
            "turn_order": entry.turn_order,
            "is_me": player is not None and entry.pk == player.pk,
        }
        for entry in game.players.select_related("user").all()
    ]

    round_payload = None
    if round_obj is not None:
        ended = round_obj.ended_at is not None
        elapsed = (now - round_obj.started_at).total_seconds()
        am_drawer = player is not None and round_obj.drawer_id == player.pk
        strokes = list(round_obj.strokes.filter(sequence__gt=since_sequence))
        found = list(
            round_obj.guesses.filter(is_correct=True).select_related("player__user").order_by("elapsed_ms")
        )
        round_payload = {
            "number": round_obj.number,
            "total": game.round_count,
            "drawer": round_obj.drawer.user.get_username(),
            "am_drawer": am_drawer,
            # Le mot n'est envoyé qu'au dessinateur, ou à tous une fois la
            # manche terminée.
            "word": round_obj.pokemon_card.name_fr if (am_drawer or ended) else None,
            "seconds_left": 0 if ended else max(0, round(ROUND_SECONDS - elapsed)),
            "round_seconds": ROUND_SECONDS,
            "ended": ended,
            "i_found": any(guess.player_id == getattr(player, "pk", None) for guess in found),
            "strokes": [
                {
                    "sequence": stroke.sequence,
                    "points": stroke.points,
                    "color": stroke.color,
                    "width": stroke.width,
                    "is_clear": stroke.is_clear,
                }
                for stroke in strokes
            ],
            "last_sequence": round_obj.strokes.aggregate(top=Max("sequence"))["top"] or 0,
            "found": [
                {
                    "username": guess.player.user.get_username(),
                    "seconds": round(guess.elapsed_ms / 1000, 1),
                    "points": guess.points,
                }
                for guess in found
            ],
            "my_guesses": [
                {"text": guess.text, "is_correct": guess.is_correct, "points": guess.points}
                for guess in (
                    round_obj.guesses.filter(player=player).order_by("created_at") if player else []
                )
            ],
        }

    return {
        "game_id": str(game.id),
        "status": game.status,
        "turn_revision": game.turn_revision,
        "round_count": game.round_count,
        "is_host": game.created_by_id == user.id,
        "is_player": player is not None,
        "min_players": MIN_PLAYERS,
        "players": players_payload,
        "round": round_payload,
    }


def get_lobby_state(user) -> dict:
    open_games = (
        PictionaryGame.objects.filter(status=PictionaryGame.Status.EN_ATTENTE)
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
