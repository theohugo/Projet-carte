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

from .i18n import pokemon_name, text
from .models import Game, Move, Pawn, Player

MIN_PLAYERS = 2
MAX_PLAYERS = 4
PAWNS_PER_PLAYER = 4
TRACK_LENGTH = 40
FINAL_LANE_LENGTH = 4
FINISH_POSITION = TRACK_LENGTH + FINAL_LANE_LENGTH - 1
MAX_BOTS = 3
MAX_AUTOMATIC_BOT_ACTIONS = 64

# Chaque dresseur commence dans un quart différent du plateau.
START_OFFSETS = (0, 10, 20, 30)
PLAYER_COLORS = ("leaf", "flame", "wave", "spark")

# Les refuges ne permettent aucune capture. Les quatre cases de départ en
# font partie afin qu'un pion puisse sortir même si la case est occupée.
SAFE_CELLS = frozenset({0, 5, 10, 15, 20, 25, 30, 35})

# Raccourcis symétriques : chaque quart contient un tremplin de quatre cases.
SHORTCUTS = {3: 7, 13: 17, 23: 27, 33: 37}

STARTERS = (
    {"pokedex_id": 1, "name": "Bulbizarre", "name_en": "Bulbasaur"},
    {"pokedex_id": 4, "name": "Salamèche", "name_en": "Charmander"},
    {"pokedex_id": 7, "name": "Carapuce", "name_en": "Squirtle"},
    {"pokedex_id": 25, "name": "Pikachu", "name_en": "Pikachu"},
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
        return text(
            "La course a avancé entre-temps. Le plateau a été actualisé.",
            "The race moved on in the meantime. The board was refreshed.",
        )


def _lock_game(game_id) -> Game:
    return Game.objects.select_for_update().get(pk=game_id)


def _get_player(game: Game, user) -> Player:
    player = game.players.select_related("user", "starter_card").filter(user=user).first()
    if player is None:
        raise StarterRacePermissionError(
            text("Vous ne participez pas à cette course.", "You are not in this race.")
        )
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
            text(
                "Le catalogue doit contenir %(name)s (Pokédex n°%(number)s).",
                "The catalogue must contain %(name)s (Pokédex No. %(number)s).",
            )
            % {
                "name": text(descriptor["name"], descriptor["name_en"]),
                "number": descriptor["pokedex_id"],
            }
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


def _available_turn_order(game: Game) -> int:
    occupied = set(game.players.values_list("turn_order", flat=True))
    return next(order for order in range(MAX_PLAYERS) if order not in occupied)


def _read_die(rng=None) -> int:
    """Tire le dé. ``rng`` peut être un objet ``randint`` ou un callable."""

    source = rng if rng is not None else random.SystemRandom()
    value = source.randint(1, 6) if hasattr(source, "randint") else source()
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 6:
        raise StarterRaceError(
            text(
                "Le générateur de dé doit produire un entier entre 1 et 6.",
                "The die generator must return an integer from 1 to 6.",
            )
        )
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
        raise StarterRaceStateError(text("Cette course a déjà commencé.", "This race has already started."))

    if game.players.count() >= MAX_PLAYERS:
        raise StarterRaceStateError(text("Cette course est complète.", "This race is full."))

    turn_order = _available_turn_order(game)
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
def add_bot(game_id, user) -> tuple[Game, Player]:
    game = _lock_game(game_id)
    _get_player(game, user)
    if game.created_by_id != user.id:
        raise StarterRacePermissionError(
            text("Seul l'hôte peut ajouter un bot.", "Only the host can add a bot.")
        )
    if game.status != Game.Status.EN_ATTENTE:
        raise StarterRaceStateError(
            text("Les bots se règlent avant le départ.", "Bots can only be changed before the race.")
        )
    if game.players.count() >= MAX_PLAYERS or game.players.filter(user__isnull=True).count() >= MAX_BOTS:
        raise StarterRaceStateError(text("Cette course est complète.", "This race is full."))

    turn_order = _available_turn_order(game)
    used_names = set(game.players.exclude(bot_name="").values_list("bot_name", flat=True))
    bot_name = next(name for name in ("Bot 1", "Bot 2", "Bot 3") if name not in used_names)
    player = Player.objects.create(
        game=game,
        user=None,
        bot_name=bot_name,
        starter_card=_starter_card_for_order(turn_order),
        turn_order=turn_order,
    )
    Pawn.objects.bulk_create([Pawn(player=player, number=number) for number in range(PAWNS_PER_PLAYER)])
    _bump_revision(game)
    return game, player


@transaction.atomic
def remove_bot(game_id, user, player_id: int) -> Game:
    game = _lock_game(game_id)
    _get_player(game, user)
    if game.created_by_id != user.id:
        raise StarterRacePermissionError(
            text("Seul l'hôte peut retirer un bot.", "Only the host can remove a bot.")
        )
    if game.status != Game.Status.EN_ATTENTE:
        raise StarterRaceStateError(
            text("Les bots se règlent avant le départ.", "Bots can only be changed before the race.")
        )
    bot = game.players.filter(pk=player_id, user__isnull=True).first()
    if bot is None:
        raise StarterRaceStateError(text("Bot introuvable.", "Bot not found."))
    bot.delete()
    _bump_revision(game)
    return game


@transaction.atomic
def start_game(game_id, user, expected_revision: int | None = None) -> Game:
    game = _lock_game(game_id)
    _get_player(game, user)
    if expected_revision is not None:
        _assert_revision(game, expected_revision)
    if game.created_by_id != user.id:
        raise StarterRacePermissionError(
            text("Seul l'hôte peut lancer la course.", "Only the host can start the race.")
        )
    if game.status != Game.Status.EN_ATTENTE:
        raise StarterRaceStateError(text("Cette course a déjà commencé.", "This race has already started."))
    if game.players.count() < MIN_PLAYERS:
        raise StarterRaceStateError(
            text(
                "Il faut au moins 2 joueurs pour lancer la course.",
                "At least 2 players are needed to start the race.",
            )
        )

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
        raise StarterRaceStateError(text("La course n'est pas en cours.", "The race is not in progress."))
    if game.current_turn_id != player.id:
        raise StarterRacePermissionError(text("Ce n'est pas votre tour.", "It is not your turn."))
    if game.pending_roll is not None:
        raise StarterRaceStateError(
            text("Choisissez d'abord un pion à déplacer.", "Choose a pawn to move first.")
        )

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


def _apply_move_locked(game: Game, player: Player, pawn: Pawn) -> Game:
    """Resolve one already-rolled move while the game row is locked."""

    roll = game.pending_roll
    if roll is None:
        raise StarterRaceStateError(
            text("Lancez le dé avant de choisir un pion.", "Roll the die before choosing a pawn.")
        )
    destination, shortcut_from, shortcut_to = _project_position(pawn, roll)
    if destination is None:
        raise StarterRaceStateError(
            text(
                "Ce pion ne peut pas avancer avec ce lancer.",
                "This pawn cannot move with that roll.",
            )
        )

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
                    "username": opponent_pawn.player.display_name,
                    "pawn_number": opponent_pawn.number,
                    "starter_name": pokemon_name(opponent_pawn.player.starter_card),
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
        human_users = [entry.user for entry in participants if not entry.is_bot]
        human_winner_ids = {player.user_id} if not player.is_bot else set()
        record_completed_game(human_users, human_winner_ids)
    elif not grants_extra_turn:
        game.current_turn = _next_player(game, player)
        update_fields.append("current_turn")
    _bump_revision(game, *update_fields)
    return game


@transaction.atomic
def move_pawn(game_id, user, pawn_id: int, expected_revision: int) -> Game:
    """Déplace le pion choisi, applique raccourci, captures et fin de tour."""

    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != Game.Status.EN_COURS:
        raise StarterRaceStateError(text("La course n'est pas en cours.", "The race is not in progress."))
    if game.current_turn_id != player.id:
        raise StarterRacePermissionError(text("Ce n'est pas votre tour.", "It is not your turn."))
    if game.pending_roll is None:
        raise StarterRaceStateError(
            text("Lancez le dé avant de choisir un pion.", "Roll the die before choosing a pawn.")
        )

    try:
        pawn = player.pawns.select_for_update().select_related("player").get(pk=pawn_id)
    except Pawn.DoesNotExist as exc:
        raise StarterRacePermissionError(
            text("Ce pion ne vous appartient pas.", "This pawn does not belong to you.")
        ) from exc

    return _apply_move_locked(game, player, pawn)


def _bot_pawn_score(game: Game, pawn: Pawn, roll: int) -> tuple:
    destination, shortcut_from, _shortcut_to = _project_position(pawn, roll)
    if destination is None:
        return (-1,)
    landing_global = global_position(pawn.player, destination)
    captures = 0
    if landing_global is not None and landing_global not in SAFE_CELLS:
        opponents = (
            Pawn.objects.select_related("player")
            .filter(
                player__game=game,
                position__gte=0,
                position__lt=TRACK_LENGTH,
            )
            .exclude(player=pawn.player)
        )
        captures = sum(
            global_position(candidate.player, candidate.position) == landing_global for candidate in opponents
        )
    return (
        destination == FINISH_POSITION,
        captures,
        shortcut_from is not None,
        destination,
        -pawn.number,
    )


def _choose_bot_pawn(game: Game, player: Player, roll: int) -> Pawn:
    legal = _legal_pawns(player, roll)
    return max(legal, key=lambda pawn: _bot_pawn_score(game, pawn, roll))


@transaction.atomic
def _play_one_bot_action(game_id, *, rng=None, stop_after_roll=False) -> Game:
    game = _lock_game(game_id)
    if game.status != Game.Status.EN_COURS or game.current_turn_id is None:
        return game
    player = (
        game.players.select_for_update().select_related("user", "starter_card").get(pk=game.current_turn_id)
    )
    if not player.is_bot:
        return game

    if game.pending_roll is None:
        roll = _read_die(rng)
        legal_pawns = _legal_pawns(player, roll)
        if not legal_pawns:
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
        game.pending_roll = roll
        _bump_revision(game, "pending_roll")
        if stop_after_roll:
            return game

    pawn = _choose_bot_pawn(game, player, game.pending_roll)
    pawn = player.pawns.select_for_update().select_related("player").get(pk=pawn.pk)
    return _apply_move_locked(game, player, pawn)


def advance_bot_step(game_id, *, rng=None) -> Game:
    """Reveal exactly one bot phase so the browser can animate it faithfully."""

    return _play_one_bot_action(game_id, rng=rng, stop_after_roll=True)


@transaction.atomic
def _release_pathological_bot_chain(game_id) -> Game:
    """Never leave a room blocked if a custom RNG returns endless sixes."""

    game = _lock_game(game_id)
    if game.status != Game.Status.EN_COURS or game.current_turn_id is None:
        return game
    current = game.players.select_related("user").get(pk=game.current_turn_id)
    if not current.is_bot:
        return game
    players = list(game.players.order_by("turn_order"))
    current_index = next(index for index, player in enumerate(players) if player.pk == current.pk)
    human = None
    for offset in range(1, len(players) + 1):
        candidate = players[(current_index + offset) % len(players)]
        if not candidate.is_bot:
            human = candidate
            break
    if human is None:
        return game
    game.pending_roll = None
    game.current_turn = human
    _bump_revision(game, "pending_roll", "current_turn")
    return game


def advance_bot_turns(game_id, *, rng=None, max_actions: int = MAX_AUTOMATIC_BOT_ACTIONS) -> Game:
    """Play every consecutive bot turn and give control back to a human."""

    game = Game.objects.get(pk=game_id)
    for _ in range(max_actions):
        if game.status != Game.Status.EN_COURS or game.current_turn_id is None:
            return game
        current = game.players.only("user_id").get(pk=game.current_turn_id)
        if not current.is_bot:
            return game
        game = _play_one_bot_action(game.id, rng=rng)
    return _release_pathological_bot_chain(game.id)


def _player_brief(player: Player | None) -> dict | None:
    if player is None:
        return None
    return {
        "id": player.id,
        "username": player.display_name,
        "turn_order": player.turn_order,
        "is_bot": player.is_bot,
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


def _localized_captures(captures: list[dict], players_by_id: dict[int, Player]) -> list[dict]:
    """Render stored capture history in the language of the current request."""

    localized = []
    for capture in captures:
        item = dict(capture)
        player = players_by_id.get(item.get("player_id"))
        if player is not None:
            item["starter_name"] = pokemon_name(player.starter_card)
        localized.append(item)
    return localized


def serialize_game_state(game: Game, user) -> dict:
    """Expose uniquement l'état de plateau public, jamais les données du compte."""

    pawn_queryset = Pawn.objects.order_by("number")
    players = list(
        game.players.select_related("user", "starter_card")
        .prefetch_related(Prefetch("pawns", queryset=pawn_queryset))
        .order_by("turn_order")
    )
    players_by_id = {player.id: player for player in players}
    me = next((candidate for candidate in players if candidate.user_id == user.id), None)
    if me is None:
        raise StarterRacePermissionError(
            text("Vous ne participez pas à cette course.", "You are not in this race.")
        )

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
        "bot_count": sum(player.is_bot for player in players),
        "can_add_bot": (
            game.status == Game.Status.EN_ATTENTE
            and game.created_by_id == user.id
            and len(players) < MAX_PLAYERS
            and sum(player.is_bot for player in players) < MAX_BOTS
        ),
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
                    "name": pokemon_name(player.starter_card),
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
                "captured_pawns": _localized_captures(move.captured_pawns, players_by_id),
                "was_pass": move.was_pass,
                "grants_extra_turn": move.grants_extra_turn,
                "created_at": move.created_at.isoformat(),
            }
            for move in moves
        ],
    }


def get_lobby_state(user) -> dict:
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    open_games = list(
        Game.objects.filter(status=Game.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
        .order_by("-created_at")
    )
    my_games = (
        list(
            Game.objects.filter(players__user=user)
            .select_related("created_by", "winner__user")
            .annotate(player_count=Count("players"))
            .distinct()
            .order_by("-created_at")
        )
        if is_authenticated
        else []
    )
    return {
        "open_games": [
            {
                "id": str(game.id),
                "host": game.created_by.get_username(),
                "player_count": game.player_count,
                "max_players": MAX_PLAYERS,
                "is_mine": is_authenticated and game.created_by_id == user.id,
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
                "winner": game.winner.display_name if game.winner_id else None,
            }
            for game in my_games
        ],
        "my_game_ids": [str(game.id) for game in my_games],
    }


# Noms courts utiles aux consommateurs qui considèrent le moteur comme une
# machine à actions ``roll`` / ``move``.
roll = roll_dice
move = move_pawn
