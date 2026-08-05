"""Moteur transactionnel de la Course des Starters.

La position d'un pion est relative à sa propre case de départ. Cela rend le
couloir final naturellement privé tout en permettant de convertir les cases
0..39 en coordonnées communes pour les captures et l'affichage.
"""

import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Max, Prefetch
from django.utils import timezone

from game.models import PokemonCard
from game.results import record_completed_game

from .models import Game, Move, Pawn, Player

MIN_PLAYERS = 2
MAX_PLAYERS = 4
PAWNS_PER_PLAYER = 4
TRACK_LENGTH = 40
FINAL_LANE_LENGTH = 4
FINISH_POSITION = TRACK_LENGTH + FINAL_LANE_LENGTH - 1

# Chaque dresseur commence dans un quart différent du plateau.
START_OFFSETS = (0, 10, 20, 30)
PLAYER_COLORS = ("leaf", "flame", "wave", "spark")

# Les refuges ne permettent aucune capture. Les quatre cases de départ en
# font partie afin qu'un pion puisse sortir même si la case est occupée.
SAFE_CELLS = frozenset({0, 5, 10, 15, 20, 25, 30, 35})

# Raccourcis symétriques : chaque quart contient un tremplin de quatre cases.
SHORTCUTS = {3: 7, 13: 17, 23: 27, 33: 37}

STARTERS = (
    {"pokedex_id": 1, "name": "Bulbizarre"},
    {"pokedex_id": 4, "name": "Salamèche"},
    {"pokedex_id": 7, "name": "Carapuce"},
    {"pokedex_id": 25, "name": "Pikachu"},
)


class StarterRaceError(Exception):
    """Erreur métier dont le message peut être présenté au joueur."""


class StarterRacePermissionError(StarterRaceError):
    pass


class StarterRaceStateError(StarterRaceError):
    pass


class StarterCatalogError(StarterRaceError):
    pass


@dataclass(frozen=True)
class StaleRevisionError(StarterRaceError):
    expected: int
    actual: int

    def __str__(self):
        return "La course a avancé entre-temps. Le plateau a été actualisé."


def _lock_game(game_id) -> Game:
    return Game.objects.select_for_update().get(pk=game_id)


def _get_player(game: Game, user) -> Player:
    player = game.players.select_related("user", "starter_card").filter(user=user).first()
    if player is None:
        raise StarterRacePermissionError("Vous ne participez pas à cette course.")
    return player


def _assert_revision(game: Game, expected_revision: int):
    if expected_revision != game.turn_revision:
        raise StaleRevisionError(expected=expected_revision, actual=game.turn_revision)


def _bump_revision(game: Game, *update_fields: str):
    game.turn_revision += 1
    fields = list(dict.fromkeys([*update_fields, "turn_revision"]))
    game.save(update_fields=fields)


def _starter_card_for_order(turn_order: int) -> PokemonCard:
    descriptor = STARTERS[turn_order]
    card = PokemonCard.objects.filter(pokedex_id=descriptor["pokedex_id"]).first()
    if card is None:
        raise StarterCatalogError(
            f"Le catalogue doit contenir {descriptor['name']} (Pokédex n°{descriptor['pokedex_id']})."
        )
    return card


def get_starter_cards() -> list[PokemonCard]:
    """Renvoie les quatre artworks dans l'ordre des places du plateau."""

    cards = PokemonCard.objects.filter(pokedex_id__in=[entry["pokedex_id"] for entry in STARTERS])
    by_pokedex_id = {card.pokedex_id: card for card in cards}
    return [by_pokedex_id[entry["pokedex_id"]] for entry in STARTERS if entry["pokedex_id"] in by_pokedex_id]


def global_position(player: Player, progress: int) -> int | None:
    """Convertit une progression relative en case de la piste commune."""

    if not 0 <= progress < TRACK_LENGTH:
        return None
    return (START_OFFSETS[player.turn_order] + progress) % TRACK_LENGTH


def _progress_for_global(player: Player, cell: int) -> int:
    return (cell - START_OFFSETS[player.turn_order]) % TRACK_LENGTH


def _project_position(pawn: Pawn, roll: int) -> tuple[int | None, int | None, int | None]:
    """Calcule la destination et, le cas échéant, le raccourci emprunté."""

    if pawn.position == Pawn.HOME:
        return (0, None, None) if roll == 6 else (None, None, None)
    if pawn.position == FINISH_POSITION:
        return None, None, None

    projected = pawn.position + roll
    if projected > FINISH_POSITION:
        return None, None, None
    if projected >= TRACK_LENGTH:
        return projected, None, None

    landing_cell = global_position(pawn.player, projected)
    shortcut_to = SHORTCUTS.get(landing_cell)
    if shortcut_to is None:
        return projected, None, None

    shortcut_progress = _progress_for_global(pawn.player, shortcut_to)
    # Tous les raccourcis avancent de quatre cases. Cette garde empêche une
    # future modification de configuration de faire reculer un pion.
    if shortcut_progress <= projected or shortcut_progress >= TRACK_LENGTH:
        return projected, None, None
    return shortcut_progress, landing_cell, shortcut_to


def _legal_pawns(player: Player, roll: int) -> list[Pawn]:
    pawns = list(player.pawns.select_related("player").order_by("number"))
    return [pawn for pawn in pawns if _project_position(pawn, roll)[0] is not None]


def _next_move_sequence(game: Game) -> int:
    return (game.moves.aggregate(latest=Max("sequence"))["latest"] or 0) + 1


def _next_player(game: Game, player: Player) -> Player:
    players = list(game.players.order_by("turn_order"))
    current_index = next(index for index, candidate in enumerate(players) if candidate.pk == player.pk)
    return players[(current_index + 1) % len(players)]


def _read_die(rng=None) -> int:
    """Tire le dé. ``rng`` peut être un objet ``randint`` ou un callable."""

    source = rng if rng is not None else random.SystemRandom()
    value = source.randint(1, 6) if hasattr(source, "randint") else source()
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 6:
        raise StarterRaceError("Le générateur de dé doit produire un entier entre 1 et 6.")
    return value


@transaction.atomic
def create_game(user) -> Game:
    starter = _starter_card_for_order(0)
    game = Game.objects.create(created_by=user)
    player = Player.objects.create(game=game, user=user, starter_card=starter, turn_order=0)
    Pawn.objects.bulk_create([Pawn(player=player, number=number) for number in range(PAWNS_PER_PLAYER)])
    return game


@transaction.atomic
def join_game(game_id, user) -> tuple[Game, Player]:
    game = _lock_game(game_id)
    existing = game.players.filter(user=user).first()
    if existing is not None:
        return game, existing
    if game.status != Game.Status.EN_ATTENTE:
        raise StarterRaceStateError("Cette course a déjà commencé.")

    turn_order = game.players.count()
    if turn_order >= MAX_PLAYERS:
        raise StarterRaceStateError("Cette course est complète.")

    starter = _starter_card_for_order(turn_order)
    player = Player.objects.create(
        game=game,
        user=user,
        starter_card=starter,
        turn_order=turn_order,
    )
    Pawn.objects.bulk_create([Pawn(player=player, number=number) for number in range(PAWNS_PER_PLAYER)])
    _bump_revision(game)
    return game, player


@transaction.atomic
def start_game(game_id, user, expected_revision: int | None = None) -> Game:
    game = _lock_game(game_id)
    _get_player(game, user)
    if expected_revision is not None:
        _assert_revision(game, expected_revision)
    if game.created_by_id != user.id:
        raise StarterRacePermissionError("Seul l'hôte peut lancer la course.")
    if game.status != Game.Status.EN_ATTENTE:
        raise StarterRaceStateError("Cette course a déjà commencé.")
    if game.players.count() < MIN_PLAYERS:
        raise StarterRaceStateError("Il faut au moins 2 joueurs pour lancer la course.")

    game.status = Game.Status.EN_COURS
    game.current_turn = game.players.get(turn_order=0)
    game.pending_roll = None
    game.started_at = timezone.now()
    _bump_revision(game, "status", "current_turn", "pending_roll", "started_at")
    return game


@transaction.atomic
def roll_dice(game_id, user, expected_revision: int, *, rng=None) -> Game:
    """Lance le dé, ou passe automatiquement si aucun pion ne peut jouer."""

    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != Game.Status.EN_COURS:
        raise StarterRaceStateError("La course n'est pas en cours.")
    if game.current_turn_id != player.id:
        raise StarterRacePermissionError("Ce n'est pas votre tour.")
    if game.pending_roll is not None:
        raise StarterRaceStateError("Choisissez d'abord un pion à déplacer.")

    roll = _read_die(rng)
    legal_pawns = _legal_pawns(player, roll)
    if legal_pawns:
        game.pending_roll = roll
        _bump_revision(game, "pending_roll")
        return game

    grants_extra_turn = roll == 6
    Move.objects.create(
        game=game,
        player=player,
        sequence=_next_move_sequence(game),
        roll=roll,
        was_pass=True,
        grants_extra_turn=grants_extra_turn,
    )
    if not grants_extra_turn:
        game.current_turn = _next_player(game, player)
    _bump_revision(game, "current_turn")
    return game


@transaction.atomic
def move_pawn(game_id, user, pawn_id: int, expected_revision: int) -> Game:
    """Déplace le pion choisi, applique raccourci, captures et fin de tour."""

    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != Game.Status.EN_COURS:
        raise StarterRaceStateError("La course n'est pas en cours.")
    if game.current_turn_id != player.id:
        raise StarterRacePermissionError("Ce n'est pas votre tour.")
    if game.pending_roll is None:
        raise StarterRaceStateError("Lancez le dé avant de choisir un pion.")

    try:
        pawn = player.pawns.select_for_update().select_related("player").get(pk=pawn_id)
    except Pawn.DoesNotExist as exc:
        raise StarterRacePermissionError("Ce pion ne vous appartient pas.") from exc

    roll = game.pending_roll
    destination, shortcut_from, shortcut_to = _project_position(pawn, roll)
    if destination is None:
        raise StarterRaceStateError("Ce pion ne peut pas avancer avec ce lancer.")

    from_position = pawn.position
    pawn.position = destination
    pawn.save(update_fields=["position"])

    captured = []
    landing_global = global_position(player, destination)
    if landing_global is not None and landing_global not in SAFE_CELLS:
        opponents = (
            Pawn.objects.select_for_update()
            .select_related("player__user", "player__starter_card")
            .filter(player__game=game)
            .exclude(player=player)
            .filter(position__gte=0, position__lt=TRACK_LENGTH)
        )
        for opponent_pawn in opponents:
            if global_position(opponent_pawn.player, opponent_pawn.position) != landing_global:
                continue
            captured.append(
                {
                    "player_id": opponent_pawn.player_id,
                    "username": opponent_pawn.player.user.get_username(),
                    "pawn_number": opponent_pawn.number,
                    "starter_name": opponent_pawn.player.starter_card.name_fr,
                }
            )
            opponent_pawn.position = Pawn.HOME
            opponent_pawn.save(update_fields=["position"])

    has_won = not player.pawns.exclude(position=FINISH_POSITION).exists()
    grants_extra_turn = roll == 6 and not has_won
    Move.objects.create(
        game=game,
        player=player,
        pawn=pawn,
        sequence=_next_move_sequence(game),
        roll=roll,
        from_position=from_position,
        to_position=destination,
        shortcut_from=shortcut_from,
        shortcut_to=shortcut_to,
        captured_pawns=captured,
        grants_extra_turn=grants_extra_turn,
    )

    game.pending_roll = None
    update_fields = ["pending_roll"]
    if has_won:
        game.status = Game.Status.TERMINEE
        game.winner = player
        game.current_turn = None
        game.finished_at = timezone.now()
        update_fields.extend(["status", "winner", "current_turn", "finished_at"])
        participants = list(game.players.select_related("user"))
        record_completed_game((entry.user for entry in participants), {player.user_id})
    elif not grants_extra_turn:
        game.current_turn = _next_player(game, player)
        update_fields.append("current_turn")
    _bump_revision(game, *update_fields)
    return game


def _player_brief(player: Player | None) -> dict | None:
    if player is None:
        return None
    return {
        "id": player.id,
        "username": player.user.get_username(),
        "turn_order": player.turn_order,
    }


def _pawn_payload(pawn: Pawn) -> dict:
    common_position = global_position(pawn.player, pawn.position)
    if pawn.position == Pawn.HOME:
        zone = "HOME"
        final_index = None
    elif pawn.position == FINISH_POSITION:
        zone = "FINISHED"
        final_index = FINAL_LANE_LENGTH - 1
    elif pawn.position >= TRACK_LENGTH:
        zone = "FINAL_LANE"
        final_index = pawn.position - TRACK_LENGTH
    else:
        zone = "TRACK"
        final_index = None
    return {
        "id": pawn.id,
        "number": pawn.number,
        "position": pawn.position,
        "zone": zone,
        "global_position": common_position,
        "final_index": final_index,
        "is_finished": pawn.is_finished,
    }


def serialize_game_state(game: Game, user) -> dict:
    """Expose uniquement l'état de plateau public, jamais les données du compte."""

    pawn_queryset = Pawn.objects.order_by("number")
    players = list(
        game.players.select_related("user", "starter_card")
        .prefetch_related(Prefetch("pawns", queryset=pawn_queryset))
        .order_by("turn_order")
    )
    me = next((candidate for candidate in players if candidate.user_id == user.id), None)
    if me is None:
        raise StarterRacePermissionError("Vous ne participez pas à cette course.")

    current_turn = next((entry for entry in players if entry.id == game.current_turn_id), None)
    winner = next((entry for entry in players if entry.id == game.winner_id), None)
    is_my_turn = game.status == Game.Status.EN_COURS and game.current_turn_id == me.id
    legal_pawn_ids = []
    if is_my_turn and game.pending_roll is not None:
        legal_pawn_ids = [pawn.id for pawn in _legal_pawns(me, game.pending_roll)]

    moves = list(game.moves.select_related("player__user", "pawn").order_by("-sequence")[:20])
    moves.reverse()

    return {
        "game_id": str(game.id),
        "status": game.status,
        "turn_revision": game.turn_revision,
        "min_players": MIN_PLAYERS,
        "max_players": MAX_PLAYERS,
        "is_host": game.created_by_id == user.id,
        "is_my_turn": is_my_turn,
        "can_start": (
            game.status == Game.Status.EN_ATTENTE
            and game.created_by_id == user.id
            and len(players) >= MIN_PLAYERS
        ),
        "can_roll": is_my_turn and game.pending_roll is None,
        "can_move": is_my_turn and game.pending_roll is not None,
        "legal_pawn_ids": legal_pawn_ids,
        "pending_roll": game.pending_roll,
        "current_turn": _player_brief(current_turn),
        "winner": _player_brief(winner),
        "me": _player_brief(me),
        "players": [
            {
                **_player_brief(player),
                "color": PLAYER_COLORS[player.turn_order],
                "start_cell": START_OFFSETS[player.turn_order],
                "starter": {
                    "id": player.starter_card_id,
                    "pokedex_id": player.starter_card.pokedex_id,
                    "name": player.starter_card.name_fr,
                    "sprite_url": player.starter_card.sprite_url,
                },
                "finished_count": sum(pawn.is_finished for pawn in player.pawns.all()),
                "pawns": [_pawn_payload(pawn) for pawn in player.pawns.all()],
            }
            for player in players
        ],
        "board": {
            "track_length": TRACK_LENGTH,
            "final_lane_length": FINAL_LANE_LENGTH,
            "safe_cells": sorted(SAFE_CELLS),
            "shortcuts": [{"from": start, "to": end} for start, end in SHORTCUTS.items()],
        },
        "moves": [
            {
                "sequence": move.sequence,
                "player": _player_brief(move.player),
                "pawn_number": move.pawn.number if move.pawn is not None else None,
                "roll": move.roll,
                "from_position": move.from_position,
                "to_position": move.to_position,
                "shortcut_from": move.shortcut_from,
                "shortcut_to": move.shortcut_to,
                "captured_pawns": move.captured_pawns,
                "was_pass": move.was_pass,
                "grants_extra_turn": move.grants_extra_turn,
                "created_at": move.created_at.isoformat(),
            }
            for move in moves
        ],
    }


def get_lobby_state(user) -> dict:
    open_games = list(
        Game.objects.filter(status=Game.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
        .order_by("-created_at")
    )
    my_games = list(
        Game.objects.filter(players__user=user)
        .select_related("created_by", "winner__user")
        .annotate(player_count=Count("players"))
        .distinct()
        .order_by("-created_at")
    )
    return {
        "open_games": [
            {
                "id": str(game.id),
                "host": game.created_by.get_username(),
                "player_count": game.player_count,
                "max_players": MAX_PLAYERS,
                "is_mine": game.created_by_id == user.id,
            }
            for game in open_games
            if game.player_count < MAX_PLAYERS
        ],
        "my_games": [
            {
                "id": str(game.id),
                "host": game.created_by.get_username(),
                "status": game.status,
                "player_count": game.player_count,
                "winner": game.winner.user.get_username() if game.winner_id else None,
            }
            for game in my_games
        ],
        "my_game_ids": [str(game.id) for game in my_games],
    }


# Noms courts utiles aux consommateurs qui considèrent le moteur comme une
# machine à actions ``roll`` / ``move``.
roll = roll_dice
move = move_pawn
