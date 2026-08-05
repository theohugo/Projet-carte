import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from game.models import PokemonCard
from game.results import record_completed_game

from .i18n import pokemon_name, text
from .models import Formation, IslandGame, IslandPlayer, Shot

GRID_SIZE = 8
FORMATION_SIZES = (2, 3, 3, 4)
BOT_NAMES = ("IA Lokhlass", "IA Aquali", "IA Carapuce")


class IslandError(Exception):
    """Erreur métier pouvant être affichée sans exposer de donnée privée."""


class IslandPermissionError(IslandError):
    pass


class IslandStateError(IslandError):
    pass


class IslandPlacementError(IslandError):
    pass


class IslandCatalogError(IslandError):
    pass


@dataclass(frozen=True)
class StaleRevisionError(IslandError):
    expected: int
    actual: int

    def __str__(self):
        return text(
            "L'état de la bataille a changé. Le plateau a été actualisé.",
            "The battle state changed. The board has been refreshed.",
        )


def _lock_game(game_id) -> IslandGame:
    return IslandGame.objects.select_for_update().get(pk=game_id)


def _get_player(game: IslandGame, user) -> IslandPlayer:
    player = game.players.select_related("user").filter(user=user).first()
    if player is None:
        raise IslandPermissionError(
            text("Vous ne participez pas à cette bataille.", "You are not taking part in this battle.")
        )
    return player


def _assert_revision(game: IslandGame, expected_revision: int):
    if expected_revision != game.turn_revision:
        raise StaleRevisionError(expected=expected_revision, actual=game.turn_revision)


def _increment_revision(game: IslandGame, *update_fields: str):
    game.turn_revision += 1
    game.save(update_fields=[*update_fields, "turn_revision"])


def _formation_cards() -> list[PokemonCard]:
    """Privilégie quatre espèces Eau, puis complète avec le catalogue.

    Les URL d'illustration viennent toujours de ``PokemonCard.sprite_url`` :
    aucune copie dessinée ou icône de remplacement n'est injectée ici.
    """

    water_cards = list(
        PokemonCard.objects.filter(Q(primary_type__slug="water") | Q(secondary_type__slug="water"))
        .distinct()
        .select_related("primary_type", "secondary_type")
    )
    selected = random.sample(water_cards, min(4, len(water_cards)))
    if len(selected) < 4:
        selected_ids = [card.pk for card in selected]
        others = list(
            PokemonCard.objects.exclude(pk__in=selected_ids).select_related("primary_type", "secondary_type")
        )
        missing = 4 - len(selected)
        if len(others) < missing:
            raise IslandCatalogError(
                text(
                    "Bataille des Îles nécessite au moins 4 Pokémon au catalogue.",
                    "Island Battle requires at least 4 Pokémon in the catalogue.",
                )
            )
        selected.extend(random.sample(others, missing))
    random.shuffle(selected)
    return selected


def _create_player(
    game: IslandGame,
    user,
    turn_order: int,
    *,
    bot_name: str = "",
    cards: list[PokemonCard] | None = None,
) -> IslandPlayer:
    cards = cards or _formation_cards()
    player = IslandPlayer.objects.create(
        game=game,
        user=user,
        bot_name=bot_name,
        turn_order=turn_order,
    )
    Formation.objects.bulk_create(
        [
            Formation(
                player=player,
                pokemon_card=card,
                slot=slot,
                size=size,
            )
            for slot, (card, size) in enumerate(zip(cards, FORMATION_SIZES, strict=True))
        ]
    )
    return player


@transaction.atomic
def create_game(user) -> IslandGame:
    # Valide le catalogue avant la création pour conserver une transaction nette.
    cards = _formation_cards()
    game = IslandGame.objects.create(created_by=user)
    _create_player(game, user, 0, cards=cards)
    return game


@transaction.atomic
def join_game(game_id, user) -> tuple[IslandGame, IslandPlayer]:
    game = _lock_game(game_id)
    existing = game.players.filter(user=user).first()
    if existing is not None:
        return game, existing
    if game.status != IslandGame.Status.EN_ATTENTE:
        raise IslandStateError(
            text("Cette bataille n'accepte plus de joueur.", "This battle is no longer accepting players.")
        )
    if game.players.count() >= 2:
        raise IslandStateError(text("Cette bataille est complète.", "This battle is full."))

    player = _create_player(game, user, 1)
    game.status = IslandGame.Status.PLACEMENT
    _increment_revision(game, "status")
    return game, player


def _next_bot_name(game: IslandGame) -> str:
    used_names = set(game.players.exclude(bot_name="").values_list("bot_name", flat=True))
    available = next((name for name in BOT_NAMES if name not in used_names), None)
    if available is not None:
        return available
    suffix = 1
    while f"IA Archipel {suffix}" in used_names:
        suffix += 1
    return f"IA Archipel {suffix}"


@transaction.atomic
def add_bot(game_id, user, expected_revision: int) -> IslandGame:
    game = _lock_game(game_id)
    _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.created_by_id != user.id:
        raise IslandPermissionError(
            text("Seul l'hôte peut ajouter une IA.", "Only the host can add an AI opponent.")
        )
    if game.status != IslandGame.Status.EN_ATTENTE:
        raise IslandStateError(
            text("L'adversaire se choisit avant le déploiement.", "Choose the opponent before deployment.")
        )
    if game.players.count() >= game.max_players:
        raise IslandStateError(text("Cette bataille est complète.", "This battle is full."))

    _create_player(game, None, 1, bot_name=_next_bot_name(game))
    _increment_revision(game)
    return game


@transaction.atomic
def remove_bot(game_id, user, bot_id: int, expected_revision: int) -> IslandGame:
    game = _lock_game(game_id)
    _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.created_by_id != user.id:
        raise IslandPermissionError(
            text("Seul l'hôte peut retirer une IA.", "Only the host can remove an AI opponent.")
        )
    if game.status != IslandGame.Status.EN_ATTENTE:
        raise IslandStateError(
            text("L'adversaire se choisit avant le déploiement.", "Choose the opponent before deployment.")
        )
    bot = game.players.select_for_update().filter(pk=bot_id, user__isnull=True).first()
    if bot is None:
        raise IslandStateError(
            text("Cette IA n'existe pas dans ce salon.", "This AI opponent is not in the lobby.")
        )

    bot.delete()
    _increment_revision(game)
    return game


def _validate_coordinate(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < GRID_SIZE:
        raise IslandPlacementError(
            text(
                f"{label} doit être comprise entre 1 et {GRID_SIZE}.",
                f"{label} must be between 1 and {GRID_SIZE}.",
            )
        )
    return value


def _placement_cells(size: int, row: int, col: int, orientation: str) -> list[tuple[int, int]]:
    _validate_coordinate(row, text("La ligne", "Row"))
    _validate_coordinate(col, text("La colonne", "Column"))
    if orientation not in Formation.Orientation.values:
        raise IslandPlacementError(
            text(
                "L'orientation doit être horizontale ou verticale.",
                "The orientation must be horizontal or vertical.",
            )
        )
    cells = [
        (
            row + (offset if orientation == Formation.Orientation.VERTICAL else 0),
            col + (offset if orientation == Formation.Orientation.HORIZONTAL else 0),
        )
        for offset in range(size)
    ]
    if any(cell_row >= GRID_SIZE or cell_col >= GRID_SIZE for cell_row, cell_col in cells):
        raise IslandPlacementError(
            text("Cette formation dépasse de la grille.", "This formation extends beyond the grid.")
        )
    return cells


def _deploy_bot_fleet(player: IslandPlayer, *, rng=None) -> None:
    """Place toute la flotte sans chevauchement à l'aide d'un backtracking borné."""

    generator = rng or random
    formations = list(player.formations.select_for_update().order_by("slot"))
    if len(formations) != len(FORMATION_SIZES):
        raise IslandStateError(text("La flotte de l'IA est incomplète.", "The AI fleet is incomplete."))

    placements: list[tuple[int, int, str] | None] = [None] * len(formations)

    def search(index: int, occupied: set[tuple[int, int]]) -> bool:
        if index == len(formations):
            return True
        formation = formations[index]
        candidates = []
        for orientation in Formation.Orientation.values:
            for row in range(GRID_SIZE):
                for col in range(GRID_SIZE):
                    try:
                        cells = set(_placement_cells(formation.size, row, col, orientation))
                    except IslandPlacementError:
                        continue
                    if not cells & occupied:
                        candidates.append((row, col, orientation, cells))
        generator.shuffle(candidates)
        for row, col, orientation, cells in candidates:
            placements[index] = (row, col, orientation)
            if search(index + 1, occupied | cells):
                return True
        placements[index] = None
        return False

    if not search(0, set()):
        raise IslandStateError(
            text("L'IA n'a pas pu déployer sa flotte.", "The AI could not deploy its fleet.")
        )

    for formation, placement in zip(formations, placements, strict=True):
        if placement is None:  # pragma: no cover - garanti par le backtracking
            raise IslandStateError(text("Placement IA incomplet.", "The AI placement is incomplete."))
        formation.start_row, formation.start_col, formation.orientation = placement
    Formation.objects.bulk_update(formations, ["start_row", "start_col", "orientation"])


@transaction.atomic
def start_bot_game(game_id, user, expected_revision: int, *, rng=None) -> IslandGame:
    game = _lock_game(game_id)
    _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.created_by_id != user.id:
        raise IslandPermissionError(
            text("Seul l'hôte peut lancer la bataille.", "Only the host can start the battle.")
        )
    if game.status != IslandGame.Status.EN_ATTENTE:
        raise IslandStateError(text("Le déploiement a déjà commencé.", "Deployment has already started."))

    # Ne pas joindre ``user`` ici : il est nullable pour les bots et
    # PostgreSQL refuse FOR UPDATE sur le côté nullable d'un OUTER JOIN.
    players = list(game.players.select_for_update().order_by("turn_order"))
    bots = [player for player in players if player.is_bot]
    if len(players) != game.max_players or len(bots) != 1:
        raise IslandStateError(
            text("Ajoutez une IA avant de commencer.", "Add an AI opponent before starting.")
        )

    bot = bots[0]
    _deploy_bot_fleet(bot, rng=rng)
    bot.is_ready = True
    bot.save(update_fields=["is_ready"])
    game.status = IslandGame.Status.PLACEMENT
    _increment_revision(game, "status")
    return game


@transaction.atomic
def place_formation(
    game_id,
    user,
    formation_id: int,
    row: int,
    col: int,
    orientation: str,
    expected_revision: int,
) -> IslandGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != IslandGame.Status.PLACEMENT:
        raise IslandStateError(
            text("Le placement n'est pas disponible maintenant.", "Placement is not available right now.")
        )
    if player.is_ready:
        raise IslandStateError(text("Votre équipe est déjà verrouillée.", "Your team is already locked."))

    formation = player.formations.select_for_update().filter(pk=formation_id).first()
    if formation is None:
        raise IslandPermissionError(
            text("Cette formation ne vous appartient pas.", "This formation does not belong to you.")
        )
    cells = set(_placement_cells(formation.size, row, col, orientation))
    occupied = {cell for other in player.formations.exclude(pk=formation.pk) for cell in other.cells}
    if cells & occupied:
        raise IslandPlacementError(
            text(
                "Deux Pokémon ne peuvent pas occuper la même case.",
                "Two Pokémon cannot occupy the same cell.",
            )
        )

    formation.start_row = row
    formation.start_col = col
    formation.orientation = orientation
    formation.save(update_fields=["start_row", "start_col", "orientation"])
    _increment_revision(game)
    return game


@transaction.atomic
def ready_player(game_id, user, expected_revision: int) -> IslandGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != IslandGame.Status.PLACEMENT:
        raise IslandStateError(
            text("La préparation n'est pas disponible maintenant.", "Preparation is not available right now.")
        )
    if player.is_ready:
        raise IslandStateError(text("Votre équipe est déjà prête.", "Your team is already ready."))
    formations = list(player.formations.select_for_update())
    if len(formations) != 4 or any(not formation.is_placed for formation in formations):
        raise IslandPlacementError(
            text(
                "Placez vos quatre Pokémon avant de confirmer.",
                "Place all four Pokémon before confirming.",
            )
        )
    all_cells = [cell for formation in formations for cell in formation.cells]
    if len(all_cells) != len(set(all_cells)):
        raise IslandPlacementError(text("Les formations se chevauchent.", "The formations overlap."))

    player.is_ready = True
    player.save(update_fields=["is_ready"])
    update_fields = []
    if game.players.count() == 2 and not game.players.filter(is_ready=False).exists():
        game.status = IslandGame.Status.EN_COURS
        game.current_turn = game.players.get(turn_order=0)
        game.started_at = timezone.now()
        update_fields = ["status", "current_turn", "started_at"]
    _increment_revision(game, *update_fields)
    return game


def _formation_at(player: IslandPlayer, row: int, col: int) -> Formation | None:
    for formation in player.formations.select_related("pokemon_card"):
        if (row, col) in formation.cells:
            return formation
    return None


def _resolve_fire_locked(
    game: IslandGame,
    shooter: IslandPlayer,
    row: int,
    col: int,
) -> tuple[IslandGame, Shot]:
    if game.status != IslandGame.Status.EN_COURS:
        raise IslandStateError(text("La bataille n'est pas en cours.", "The battle is not in progress."))
    if game.current_turn_id != shooter.id:
        raise IslandStateError(text("Ce n'est pas votre tour.", "It is not your turn."))
    _validate_coordinate(row, text("La ligne", "Row"))
    _validate_coordinate(col, text("La colonne", "Column"))
    target = game.players.select_for_update().exclude(pk=shooter.pk).get()
    if Shot.objects.filter(game=game, target=target, row=row, col=col).exists():
        raise IslandStateError(
            text("Cette coordonnée a déjà été attaquée.", "This coordinate has already been attacked.")
        )

    formation = _formation_at(target, row, col)
    if formation is None:
        result = Shot.Result.MISS
    else:
        previous_hit_cells = set(
            Shot.objects.filter(
                game=game,
                target=target,
                formation=formation,
            ).values_list("row", "col")
        )
        result = (
            Shot.Result.CAPTURED
            if set(formation.cells) == previous_hit_cells | {(row, col)}
            else Shot.Result.HIT
        )

    shot = Shot.objects.create(
        game=game,
        shooter=shooter,
        target=target,
        row=row,
        col=col,
        result=result,
        formation=formation,
    )

    total_occupied = sum(formation.size for formation in target.formations.all())
    hit_count = Shot.objects.filter(game=game, target=target, formation__isnull=False).count()
    if hit_count == total_occupied:
        game.status = IslandGame.Status.TERMINEE
        game.winner = shooter
        game.current_turn = None
        game.finished_at = timezone.now()
        update_fields = ["status", "winner", "current_turn", "finished_at"]
        participants = list(game.players.select_related("user"))
        human_players = [entry for entry in participants if not entry.is_bot]
        human_winners = {shooter.user_id} if not shooter.is_bot else set()
        record_completed_game((entry.user for entry in human_players), human_winners)
    elif result == Shot.Result.MISS:
        game.current_turn = target
        update_fields = ["current_turn"]
    else:
        # Un impact réussi conserve l'initiative ; seul un raté passe le tour.
        game.current_turn = shooter
        update_fields = ["current_turn"]
    _increment_revision(game, *update_fields)
    return game, shot


@transaction.atomic
def fire(
    game_id,
    user,
    row: int,
    col: int,
    expected_revision: int,
) -> tuple[IslandGame, Shot]:
    game = _lock_game(game_id)
    shooter = _get_player(game, user)
    _assert_revision(game, expected_revision)
    return _resolve_fire_locked(game, shooter, row, col)


def _orthogonal_neighbors(row: int, col: int) -> list[tuple[int, int]]:
    return [
        (candidate_row, candidate_col)
        for candidate_row, candidate_col in (
            (row - 1, col),
            (row + 1, col),
            (row, col - 1),
            (row, col + 1),
        )
        if 0 <= candidate_row < GRID_SIZE and 0 <= candidate_col < GRID_SIZE
    ]


def choose_bot_coordinate(game: IslandGame, bot: IslandPlayer, *, rng=None) -> tuple[int, int]:
    """Choisit un tir uniquement depuis les résultats déjà visibles par l'IA.

    La stratégie cible les voisins d'un impact non résolu, prolonge l'axe
    lorsqu'il est connu, puis chasse en damier. Elle ne lit jamais les
    ``Formation`` de l'adversaire ni leurs coordonnées secrètes.
    """

    generator = rng or random
    history = list(game.shots.filter(shooter=bot).order_by("created_at", "pk").values("row", "col", "result"))
    fired = {(entry["row"], entry["col"]) for entry in history}
    visible_hits = {(entry["row"], entry["col"]) for entry in history if entry["result"] == Shot.Result.HIT}
    captured_cells = {
        (entry["row"], entry["col"]) for entry in history if entry["result"] == Shot.Result.CAPTURED
    }
    # Une capture résout le groupe d'impacts qui lui est relié sur le radar.
    # Cette approximation volontaire peut se tromper si deux formations se
    # touchent, exactement comme le ferait un joueur humain sans information
    # secrète sur leur identité.
    impact_cells = visible_hits | captured_cells
    resolved_cells = set(captured_cells)
    frontier = list(captured_cells)
    while frontier:
        current = frontier.pop()
        for neighbor in _orthogonal_neighbors(*current):
            if neighbor in impact_cells and neighbor not in resolved_cells:
                resolved_cells.add(neighbor)
                frontier.append(neighbor)
    unresolved_hits = [
        (entry["row"], entry["col"])
        for entry in history
        if entry["result"] == Shot.Result.HIT and (entry["row"], entry["col"]) not in resolved_cells
    ]

    target_candidates: list[tuple[int, int]] = []
    if unresolved_hits:
        hit_cells = set(unresolved_hits)
        latest = unresolved_hits[-1]
        component = {latest}
        frontier = [latest]
        while frontier:
            current = frontier.pop()
            for neighbor in _orthogonal_neighbors(*current):
                if neighbor in hit_cells and neighbor not in component:
                    component.add(neighbor)
                    frontier.append(neighbor)

        rows = {row for row, _col in component}
        cols = {col for _row, col in component}
        if len(component) > 1 and len(rows) == 1:
            row = next(iter(rows))
            ordered_cols = sorted(col for _row, col in component)
            target_candidates.extend([(row, ordered_cols[0] - 1), (row, ordered_cols[-1] + 1)])
        elif len(component) > 1 and len(cols) == 1:
            col = next(iter(cols))
            ordered_rows = sorted(row for row, _col in component)
            target_candidates.extend([(ordered_rows[0] - 1, col), (ordered_rows[-1] + 1, col)])
        target_candidates.extend(
            neighbor for cell in sorted(component) for neighbor in _orthogonal_neighbors(*cell)
        )
        target_candidates = sorted(
            {
                coordinate
                for coordinate in target_candidates
                if 0 <= coordinate[0] < GRID_SIZE
                and 0 <= coordinate[1] < GRID_SIZE
                and coordinate not in fired
            }
        )

    if target_candidates:
        return generator.choice(target_candidates)

    available = [
        (row, col) for row in range(GRID_SIZE) for col in range(GRID_SIZE) if (row, col) not in fired
    ]
    if not available:
        raise IslandStateError(text("Aucune coordonnée ne reste à explorer.", "No coordinates remain."))
    hunt = [coordinate for coordinate in available if sum(coordinate) % 2 == 0]
    return generator.choice(hunt or available)


@transaction.atomic
def play_bot_turn(
    game_id,
    user,
    expected_revision: int,
    *,
    rng=None,
) -> tuple[IslandGame, Shot]:
    """Joue exactement un tir IA, déclenché par un participant humain."""

    game = _lock_game(game_id)
    _get_player(game, user)
    _assert_revision(game, expected_revision)
    if game.status != IslandGame.Status.EN_COURS:
        raise IslandStateError(text("La bataille n'est pas en cours.", "The battle is not in progress."))
    bot = game.players.select_for_update().filter(pk=game.current_turn_id, user__isnull=True).first()
    if bot is None:
        raise IslandStateError(text("Ce n'est pas le tour de l'IA.", "It is not the AI's turn."))

    row, col = choose_bot_coordinate(game, bot, rng=rng)
    return _resolve_fire_locked(game, bot, row, col)


def _serialize_card(card: PokemonCard) -> dict:
    return {
        "id": card.id,
        "pokedex_id": card.pokedex_id,
        "name": pokemon_name(card),
        "name_fr": card.name_fr,
        "name_en": card.name_en,
        "sprite_url": card.sprite_url,
    }


def _serialize_player(player: IslandPlayer | None) -> dict | None:
    if player is None:
        return None
    return {
        "id": player.id,
        "username": player.display_name,
        "is_bot": player.is_bot,
        "turn_order": player.turn_order,
        "is_ready": player.is_ready,
    }


def _serialize_formation(formation: Formation, reveal_position: bool) -> dict:
    payload = {
        "id": formation.id,
        "slot": formation.slot,
        "size": formation.size,
        "pokemon": _serialize_card(formation.pokemon_card),
        "is_placed": formation.is_placed,
    }
    if reveal_position:
        payload.update(
            {
                "row": formation.start_row,
                "col": formation.start_col,
                "orientation": formation.orientation,
                "cells": [list(cell) for cell in formation.cells],
            }
        )
    return payload


def serialize_game_state(game: IslandGame, user) -> dict:
    """Retourne un plateau personnalisé sans aucune case adverse non jouée."""

    players = list(game.players.select_related("user").order_by("turn_order"))
    me = next((player for player in players if player.user_id == user.id), None)
    if me is None:
        raise IslandPermissionError(
            text("Vous ne participez pas à cette bataille.", "You are not taking part in this battle.")
        )
    opponent = next((player for player in players if player.pk != me.pk), None)
    reveal_opponent = game.status == IslandGame.Status.TERMINEE

    own_formations = list(me.formations.select_related("pokemon_card").order_by("slot"))
    opponent_formations = (
        list(opponent.formations.select_related("pokemon_card").order_by("slot"))
        if opponent is not None
        else []
    )
    received_shots = list(
        game.shots.filter(target=me).select_related("formation__pokemon_card", "shooter__user")
    )
    fired_shots = list(
        game.shots.filter(shooter=me).select_related("formation__pokemon_card", "target__user")
    )

    def serialize_shot(shot: Shot, include_capture=True):
        payload = {
            "id": shot.id,
            "row": shot.row,
            "col": shot.col,
            "coordinate": f"{chr(65 + shot.col)}{shot.row + 1}",
            "result": shot.result,
            "created_at": shot.created_at.isoformat(),
        }
        if include_capture and shot.result == Shot.Result.CAPTURED and shot.formation_id:
            payload["captured_pokemon"] = _serialize_card(shot.formation.pokemon_card)
        return payload

    own_hit_coordinates = {(shot.row, shot.col) for shot in received_shots if shot.formation_id}
    own_payload = []
    for formation in own_formations:
        entry = _serialize_formation(formation, reveal_position=True)
        entry["hit_cells"] = [list(cell) for cell in formation.cells if cell in own_hit_coordinates]
        entry["is_captured"] = bool(formation.cells) and all(
            cell in own_hit_coordinates for cell in formation.cells
        )
        own_payload.append(entry)

    opponent_payload = (
        [_serialize_formation(formation, reveal_position=True) for formation in opponent_formations]
        if reveal_opponent
        else []
    )
    current_turn = next(
        (player for player in players if player.pk == game.current_turn_id),
        None,
    )
    winner = next((player for player in players if player.pk == game.winner_id), None)
    return {
        "game_id": str(game.id),
        "status": game.status,
        "turn_revision": game.turn_revision,
        "grid_size": GRID_SIZE,
        "is_creator": game.created_by_id == user.id,
        "is_host": game.created_by_id == user.id,
        "max_players": game.max_players,
        "can_add_bot": (
            game.status == IslandGame.Status.EN_ATTENTE
            and game.created_by_id == user.id
            and len(players) < game.max_players
        ),
        "can_start": (
            game.status == IslandGame.Status.EN_ATTENTE
            and game.created_by_id == user.id
            and len(players) == game.max_players
            and any(player.is_bot for player in players)
        ),
        "bot_turn_pending": (
            game.status == IslandGame.Status.EN_COURS and current_turn is not None and current_turn.is_bot
        ),
        "is_my_turn": game.status == IslandGame.Status.EN_COURS and game.current_turn_id == me.id,
        "can_place": game.status == IslandGame.Status.PLACEMENT and not me.is_ready,
        "can_ready": (
            game.status == IslandGame.Status.PLACEMENT
            and not me.is_ready
            and len(own_formations) == 4
            and all(formation.is_placed for formation in own_formations)
        ),
        "me": _serialize_player(me),
        "opponent": _serialize_player(opponent),
        "players": [_serialize_player(player) for player in players],
        "current_turn": _serialize_player(current_turn),
        "winner": _serialize_player(winner),
        "own_formations": own_payload,
        # Cette liste est volontairement vide avant TERMINEE, même pour une
        # formation capturée. Les tirs déjà joués suffisent à l'interface.
        "opponent_formations": opponent_payload,
        "shots_fired": [serialize_shot(shot) for shot in fired_shots],
        "shots_received": [serialize_shot(shot, include_capture=False) for shot in received_shots],
        "last_shot": (
            serialize_shot(game.shots.select_related("formation__pokemon_card").last())
            if game.shots.exists()
            else None
        ),
        "ui": {
            "result_miss": text("Raté", "Miss"),
            "result_hit": text("Touché", "Hit"),
            "result_captured": text("Capturé", "Captured"),
            "status_waiting": text("En attente", "Waiting"),
            "status_placement": text("Déploiement", "Deployment"),
            "status_battle": text("Bataille en cours", "Battle in progress"),
            "status_finished": text("Terminée", "Finished"),
            "syncing": text("Synchronisation…", "Syncing…"),
            "synced": text("Synchronisé", "Synced"),
            "reconnecting": text("Reconnexion…", "Reconnecting…"),
            "network_error": text(
                "La mer est momentanément inaccessible.",
                "The sea is temporarily unreachable.",
            ),
            "you_replay": text("Tu rejoues !", "You play again!"),
            "you_replay_inline": text("Tu rejoues", "You play again"),
            "replays": text("rejoue", "plays again"),
            "rival": text("Le rival", "Your opponent"),
            "opponent": text("l’adversaire", "your opponent"),
            "cells": text("cases", "cells"),
            "placed": text("Placé", "Placed"),
            "to_place": text("À placer", "To place"),
            "team_locked_waiting": text(
                "Équipe verrouillée · attente du rival",
                "Team locked · waiting for opponent",
            ),
            "lock_team": text("Verrouiller mon équipe", "Lock my team"),
            "select_first": text(
                "Sélectionne d'abord un Pokémon.",
                "Select a Pokémon first.",
            ),
            "position_locked_waiting": text(
                "Position verrouillée · attente du rival",
                "Position locked · waiting for opponent",
            ),
            "select_pokemon": text("Sélectionne un Pokémon", "Select a Pokémon"),
            "free_cell": text("libre", "free"),
            "unexplored": text("inexploré", "unexplored"),
            "captured_suffix": text("capturé", "captured"),
            "hits": text("touches", "hits"),
            "intact_cells": text("cases intactes", "intact cells"),
            "your_turn": text("À toi d'explorer", "Your turn to explore"),
            "turn_of": text("Tour de", "Turn:"),
            "choose_coordinate": text(
                "Choisis une coordonnée à explorer.",
                "Choose a coordinate to explore.",
            ),
            "watch_radar": text(
                "Observe le radar pendant le tour adverse.",
                "Watch the radar during your opponent's turn.",
            ),
            "no_shots": text("Aucun tir pour le moment.", "No shots yet."),
            "victory_title": text("Archipel conquis !", "Archipelago conquered!"),
            "defeat_title": text(
                "Ton équipe a été repérée",
                "Your team has been located",
            ),
            "victory_prefix": text(
                "Belle lecture du radar : tu as capturé toute l'escouade de",
                "Excellent radar work: you captured the entire squad of",
            ),
            "defeat_suffix": text(
                "a trouvé tes quatre formations. La revanche t'attend.",
                "found all four of your formations. A rematch awaits.",
            ),
            "horizontal": text("horizontal", "horizontal"),
            "vertical": text("vertical", "vertical"),
            "link_copied": text("Lien copié !", "Link copied!"),
            "invitation_copied": text(
                "Lien d'invitation copié.",
                "Invitation link copied.",
            ),
            "copy_failed": text(
                "Copie impossible. Sélectionne le lien manuellement.",
                "Could not copy. Select the link manually.",
            ),
            "your_turn_announcement": text(
                "C'est à toi d'explorer une coordonnée.",
                "It is your turn to explore a coordinate.",
            ),
            "bot_ready": text("Adversaire IA · prêt", "AI opponent · ready"),
            "human_ready": text("Capitaine humain", "Human captain"),
            "open_slot": text("Place libre", "Open slot"),
            "remove_bot": text("Retirer l'IA", "Remove AI"),
            "bot_thinking": text("L'IA analyse le radar…", "The AI is scanning the radar…"),
            "bot_initial": text("IA", "AI"),
            "max_two": text("2 joueurs maximum", "2 players maximum"),
            "waiting_title": text("Un rival manque à l'appel", "Waiting for an opponent"),
            "waiting_lead": text(
                "Partage ce lien ou ajoute une IA pour commencer.",
                "Share this link or add an AI opponent to begin.",
            ),
            "bot_joined_title": text("Ton rival IA est prêt", "Your AI opponent is ready"),
            "bot_joined_lead": text(
                "Sa flotte restera secrète. Lance le déploiement de ton équipe quand tu veux.",
                "Its fleet will stay secret. Start deploying your team when ready.",
            ),
            "start_ready": text(
                "L'IA a rejoint la table. Lancez le déploiement quand vous êtes prêt.",
                "The AI has joined. Start deployment when you are ready.",
            ),
            "table_full": text("La table est complète.", "The table is full."),
            "invite_or_bot": text(
                "Invitez un ami ou ajoutez une IA pour jouer immédiatement.",
                "Invite a friend or add an AI opponent to play now.",
            ),
        },
    }


def get_lobby_state(user) -> dict:
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    open_games = (
        IslandGame.objects.filter(status=IslandGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
        .filter(player_count__lt=2)
    )
    my_games = (
        IslandGame.objects.annotate(player_count=Count("players"))
        .filter(players__user=user)
        .select_related("winner__user")
        .distinct()
        if is_authenticated
        else IslandGame.objects.none()
    )
    return {
        "open_games": [
            {
                "id": str(game.id),
                "host": game.created_by.get_username(),
                "player_count": game.player_count,
                "status": game.status,
            }
            for game in open_games
        ],
        "my_games": [
            {
                "id": str(game.id),
                "status": game.status,
                "player_count": game.player_count,
                "winner": game.winner.display_name if game.winner_id else None,
                "turn_revision": game.turn_revision,
            }
            for game in my_games
        ],
        "my_game_ids": [str(game.id) for game in my_games],
    }
