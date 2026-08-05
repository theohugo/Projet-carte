import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from game.guests import guest_action, guest_allowed, public_lobby
from game.models import PokemonCard

from .i18n import pokemon_name, text
from .models import IslandGame, Shot
from .services import (
    IslandError,
    IslandPermissionError,
    StaleRevisionError,
    add_bot,
    fire,
    get_lobby_state,
    place_formation,
    play_bot_turn,
    ready_player,
    remove_bot,
    serialize_game_state,
    start_bot_game,
)
from .services import create_game as create_game_service
from .services import join_game as join_game_service


def _read_json_object(request):
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse(
            {"error": text("Requête JSON invalide.", "Invalid JSON request.")},
            status=400,
        )
    if not isinstance(payload, dict):
        return None, JsonResponse(
            {
                "error": text(
                    "La requête doit contenir un objet JSON.",
                    "The request must contain a JSON object.",
                )
            },
            status=400,
        )
    return payload, None


def _read_revision(payload):
    revision = payload.get("expected_turn_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return None, JsonResponse(
            {"error": text("Révision de tour invalide.", "Invalid turn revision.")},
            status=400,
        )
    return revision, None


def _read_int(payload, key, error_message):
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None, JsonResponse({"error": error_message}, status=400)
    return value, None


def _error_response(exc, game_id, user):
    if isinstance(exc, StaleRevisionError):
        game = get_object_or_404(IslandGame, pk=game_id)
        return JsonResponse(
            {
                "error": str(exc),
                "code": "stale_revision",
                "state": serialize_game_state(game, user),
            },
            status=409,
        )
    return JsonResponse(
        {"error": str(exc)},
        status=403 if isinstance(exc, IslandPermissionError) else 400,
    )


def _action_result(game, shot, *, include_capture=True):
    combo = 0
    if shot.result != Shot.Result.MISS:
        for result in (
            game.shots.filter(shooter=shot.shooter)
            .order_by("-created_at", "-pk")
            .values_list("result", flat=True)
        ):
            if result == Shot.Result.MISS:
                break
            combo += 1
    payload = {
        "row": shot.row,
        "col": shot.col,
        "coordinate": f"{chr(65 + shot.col)}{shot.row + 1}",
        "result": shot.result,
        "combo": combo,
        "keeps_turn": (game.status == IslandGame.Status.EN_COURS and game.current_turn_id == shot.shooter_id),
    }
    if include_capture:
        payload["captured_pokemon"] = (
            {
                "name": pokemon_name(shot.formation.pokemon_card),
                "name_fr": shot.formation.pokemon_card.name_fr,
                "name_en": shot.formation.pokemon_card.name_en,
                "sprite_url": shot.formation.pokemon_card.sprite_url,
            }
            if shot.result == Shot.Result.CAPTURED
            else None
        )
    return payload


@public_lobby
def lobby(request):
    open_games = (
        IslandGame.objects.filter(status=IslandGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
        .filter(player_count__lt=2)
    )
    my_games = (
        IslandGame.objects.annotate(player_count=Count("players"))
        .filter(players__user=request.user)
        .select_related("winner__user")
        .distinct()
        if request.user.is_authenticated
        else IslandGame.objects.none()
    )
    hero_cards = list(
        PokemonCard.objects.filter(Q(primary_type__slug="water") | Q(secondary_type__slug="water"))
        .distinct()
        .order_by("pokedex_id")[:4]
    )
    return render(
        request,
        "islands/lobby.html",
        {
            "open_games": open_games,
            "my_games": my_games,
            "hero_cards": hero_cards,
            "lobby_state": get_lobby_state(request.user),
        },
    )


@require_GET
def api_lobby_state(request):
    return JsonResponse(get_lobby_state(request.user))


@guest_action
@require_POST
def create_game(request):
    try:
        game = create_game_service(request.user)
    except IslandError as exc:
        messages.error(request, str(exc))
        return redirect("islands:lobby")
    return redirect("islands:game_detail", game_id=game.id)


@guest_action
@require_POST
def join_game(request, game_id):
    try:
        game, _player = join_game_service(game_id, request.user)
    except IslandGame.DoesNotExist:
        get_object_or_404(IslandGame, pk=game_id)
    except IslandError as exc:
        messages.error(request, str(exc))
        return redirect("islands:lobby")
    return redirect("islands:game_detail", game_id=game.id)


@guest_allowed
def game_detail(request, game_id):
    game = get_object_or_404(IslandGame, pk=game_id)
    if not game.players.filter(user=request.user).exists():
        player_count = game.players.count()
        can_join = game.status == IslandGame.Status.EN_ATTENTE and player_count < 2
        return render(
            request,
            "join_invitation.html",
            {
                "mode_name": text("Bataille des Îles", "Island Battle"),
                "mode_kicker": text(
                    "Stratégie · exploration · duel",
                    "Strategy · exploration · duel",
                ),
                "host_name": game.created_by.get_username(),
                "player_count": player_count,
                "max_players": 2,
                "can_join": can_join,
                "join_url": reverse("islands:join_game", kwargs={"game_id": game.id}),
                "lobby_url": reverse("islands:lobby"),
            },
            status=200 if can_join else 403,
        )
    return render(
        request,
        "islands/detail.html",
        {"game": game, "game_state": serialize_game_state(game, request.user)},
    )


@login_required
@require_GET
def api_state(request, game_id):
    game = get_object_or_404(IslandGame, pk=game_id)
    try:
        return JsonResponse(serialize_game_state(game, request.user))
    except IslandPermissionError as exc:
        return JsonResponse({"error": str(exc)}, status=403)


@login_required
@require_POST
def api_add_bot(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_revision(payload)
    if error:
        return error
    try:
        game = add_bot(game_id, request.user, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except IslandGame.DoesNotExist:
        get_object_or_404(IslandGame, pk=game_id)
    except IslandError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_remove_bot(request, game_id, bot_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_revision(payload)
    if error:
        return error
    try:
        game = remove_bot(game_id, request.user, bot_id, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except IslandGame.DoesNotExist:
        get_object_or_404(IslandGame, pk=game_id)
    except IslandError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_start(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_revision(payload)
    if error:
        return error
    try:
        game = start_bot_game(game_id, request.user, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except IslandGame.DoesNotExist:
        get_object_or_404(IslandGame, pk=game_id)
    except IslandError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_place(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_revision(payload)
    if error:
        return error
    formation_id, error = _read_int(
        payload,
        "formation_id",
        text("Formation invalide.", "Invalid formation."),
    )
    if error:
        return error
    row, error = _read_int(payload, "row", text("Ligne invalide.", "Invalid row."))
    if error:
        return error
    col, error = _read_int(payload, "col", text("Colonne invalide.", "Invalid column."))
    if error:
        return error
    orientation = payload.get("orientation")
    if not isinstance(orientation, str):
        return JsonResponse(
            {"error": text("Orientation invalide.", "Invalid orientation.")},
            status=400,
        )
    try:
        game = place_formation(
            game_id,
            request.user,
            formation_id,
            row,
            col,
            orientation,
            revision,
        )
        return JsonResponse(serialize_game_state(game, request.user))
    except IslandGame.DoesNotExist:
        get_object_or_404(IslandGame, pk=game_id)
    except IslandError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_ready(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_revision(payload)
    if error:
        return error
    try:
        game = ready_player(game_id, request.user, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except IslandGame.DoesNotExist:
        get_object_or_404(IslandGame, pk=game_id)
    except IslandError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_fire(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_revision(payload)
    if error:
        return error
    row, error = _read_int(payload, "row", text("Ligne invalide.", "Invalid row."))
    if error:
        return error
    col, error = _read_int(payload, "col", text("Colonne invalide.", "Invalid column."))
    if error:
        return error
    try:
        game, shot = fire(game_id, request.user, row, col, revision)
        state = serialize_game_state(game, request.user)
        state["action_result"] = _action_result(game, shot)
        return JsonResponse(state)
    except IslandGame.DoesNotExist:
        get_object_or_404(IslandGame, pk=game_id)
    except IslandError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_bot_turn(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_revision(payload)
    if error:
        return error
    try:
        game, shot = play_bot_turn(game_id, request.user, revision)
        state = serialize_game_state(game, request.user)
        state["action_result"] = _action_result(game, shot, include_capture=False)
        return JsonResponse(state)
    except IslandGame.DoesNotExist:
        get_object_or_404(IslandGame, pk=game_id)
    except IslandError as exc:
        return _error_response(exc, game_id, request.user)
