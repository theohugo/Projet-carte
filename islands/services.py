import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from game.models import PokemonCard
from game.results import record_completed_game

from .models import Formation, IslandGame, IslandPlayer, Shot

GRID_SIZE = 8
FORMATION_SIZES = (2, 3, 3, 4)


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
        return "L'état de la bataille a changé. Le plateau a été actualisé."


def _lock_game(game_id) -> IslandGame:
    return IslandGame.objects.select_for_update().get(pk=game_id)


def _get_player(game: IslandGame, user) -> IslandPlayer:
    player = game.players.select_related("user").filter(user=user).first()
    if player is None:
        raise IslandPermissionError("Vous ne participez pas à cette bataille.")
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
            raise IslandCatalogError("Bataille des Îles nécessite au moins 4 Pokémon au catalogue.")
        selected.extend(random.sample(others, missing))
    random.shuffle(selected)
    return selected


def _create_player(game: IslandGame, user, turn_order: int) -> IslandPlayer:
    cards = _formation_cards()
    player = IslandPlayer.objects.create(game=game, user=user, turn_order=turn_order)
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
    player = IslandPlayer.objects.create(game=game, user=user, turn_order=0)
    Formation.objects.bulk_create(
        [
            Formation(player=player, pokemon_card=card, slot=slot, size=size)
            for slot, (card, size) in enumerate(zip(cards, FORMATION_SIZES, strict=True))
        ]
    )
    return game


@transaction.atomic
def join_game(game_id, user) -> tuple[IslandGame, IslandPlayer]:
    game = _lock_game(game_id)
    existing = game.players.filter(user=user).first()
    if existing is not None:
        return game, existing
    if game.status != IslandGame.Status.EN_ATTENTE:
        raise IslandStateError("Cette bataille n'accepte plus de joueur.")
    if game.players.count() >= 2:
        raise IslandStateError("Cette bataille est complète.")

    player = _create_player(game, user, 1)
    game.status = IslandGame.Status.PLACEMENT
    _increment_revision(game, "status")
    return game, player


def _validate_coordinate(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < GRID_SIZE:
        raise IslandPlacementError(f"{label} doit être comprise entre 1 et {GRID_SIZE}.")
    return value


def _placement_cells(size: int, row: int, col: int, orientation: str) -> list[tuple[int, int]]:
    _validate_coordinate(row, "La ligne")
    _validate_coordinate(col, "La colonne")
    if orientation not in Formation.Orientation.values:
        raise IslandPlacementError("L'orientation doit être horizontale ou verticale.")
    cells = [
        (
            row + (offset if orientation == Formation.Orientation.VERTICAL else 0),
            col + (offset if orientation == Formation.Orientation.HORIZONTAL else 0),
        )
        for offset in range(size)
    ]
    if any(cell_row >= GRID_SIZE or cell_col >= GRID_SIZE for cell_row, cell_col in cells):
        raise IslandPlacementError("Cette formation dépasse de la grille.")
    return cells


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
        raise IslandStateError("Le placement n'est pas disponible maintenant.")
    if player.is_ready:
        raise IslandStateError("Votre équipe est déjà verrouillée.")

    formation = player.formations.select_for_update().filter(pk=formation_id).first()
    if formation is None:
        raise IslandPermissionError("Cette formation ne vous appartient pas.")
    cells = set(_placement_cells(formation.size, row, col, orientation))
    occupied = {cell for other in player.formations.exclude(pk=formation.pk) for cell in other.cells}
    if cells & occupied:
        raise IslandPlacementError("Deux Pokémon ne peuvent pas occuper la même case.")

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
        raise IslandStateError("La préparation n'est pas disponible maintenant.")
    if player.is_ready:
        raise IslandStateError("Votre équipe est déjà prête.")
    formations = list(player.formations.select_for_update())
    if len(formations) != 4 or any(not formation.is_placed for formation in formations):
        raise IslandPlacementError("Placez vos quatre Pokémon avant de confirmer.")
    all_cells = [cell for formation in formations for cell in formation.cells]
    if len(all_cells) != len(set(all_cells)):
        raise IslandPlacementError("Les formations se chevauchent.")

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
    if game.status != IslandGame.Status.EN_COURS:
        raise IslandStateError("La bataille n'est pas en cours.")
    if game.current_turn_id != shooter.id:
        raise IslandStateError("Ce n'est pas votre tour.")
    _validate_coordinate(row, "La ligne")
    _validate_coordinate(col, "La colonne")
    target = game.players.select_for_update().exclude(pk=shooter.pk).get()
    if Shot.objects.filter(game=game, target=target, row=row, col=col).exists():
        raise IslandStateError("Cette coordonnée a déjà été attaquée.")

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
        record_completed_game((entry.user for entry in participants), {shooter.user_id})
    else:
        game.current_turn = target
        update_fields = ["current_turn"]
    _increment_revision(game, *update_fields)
    return game, shot


def _serialize_card(card: PokemonCard) -> dict:
    return {
        "id": card.id,
        "pokedex_id": card.pokedex_id,
        "name_fr": card.name_fr,
        "name_en": card.name_en,
        "sprite_url": card.sprite_url,
    }


def _serialize_player(player: IslandPlayer | None) -> dict | None:
    if player is None:
        return None
    return {
        "id": player.id,
        "username": player.user.get_username(),
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
        raise IslandPermissionError("Vous ne participez pas à cette bataille.")
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
    }


def get_lobby_state(user) -> dict:
    open_games = (
        IslandGame.objects.filter(status=IslandGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
    )
    my_games = (
        IslandGame.objects.annotate(player_count=Count("players"))
        .filter(players__user=user)
        .select_related("winner__user")
        .distinct()
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
                "winner": game.winner.user.get_username() if game.winner_id else None,
                "turn_revision": game.turn_revision,
            }
            for game in my_games
        ],
        "my_game_ids": [str(game.id) for game in my_games],
    }
