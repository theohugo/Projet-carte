import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from game.guests import guest_allowed

from .models import RocketGame
from .services import (
    RocketError,
    RocketPermissionError,
    StaleRevisionError,
    advance_if_expired,
    create_game,
    get_lobby_state,
    join_game,
    send_message,
    serialize_game_state,
    start_game,
    start_vote,
    submit_night_action,
    submit_vote,
)


def _json_payload(request):
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "Requête JSON invalide."}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "La requête doit contenir un objet JSON."}, status=400)
    return payload, None


def _error_response(exc, game, user):
    if isinstance(exc, StaleRevisionError):
        game.refresh_from_db()
        return JsonResponse(
            {"error": str(exc), "code": "stale_revision", "state": serialize_game_state(game, user)},
            status=409,
        )
    status = 403 if isinstance(exc, RocketPermissionError) else 400
    return JsonResponse({"error": str(exc)}, status=status)


@guest_allowed
def lobby(request):
    return render(request, "rocket/lobby.html", {"lobby_state": get_lobby_state(request.user)})


@login_required
@require_GET
def api_lobby_state(request):
    return JsonResponse(get_lobby_state(request.user))


@login_required
@require_POST
def create_game_view(request):
    game = create_game(request.user)
    return redirect("rocket:game_detail", game_id=game.id)


@login_required
@require_POST
def join_game_view(request, game_id):
    try:
        join_game(game_id, request.user)
    except RocketGame.DoesNotExist:
        messages.error(request, "Cette infiltration n'existe plus.")
        return redirect("rocket:lobby")
    except RocketError as exc:
        messages.error(request, str(exc))
    return redirect("rocket:game_detail", game_id=game_id)


@login_required
@require_POST
def start_game_view(request, game_id):
    try:
        start_game(game_id, request.user)
    except RocketGame.DoesNotExist:
        messages.error(request, "Cette infiltration n'existe plus.")
        return redirect("rocket:lobby")
    except RocketError as exc:
        messages.error(request, str(exc))
    return redirect("rocket:game_detail", game_id=game_id)


@guest_allowed
def game_detail(request, game_id):
    game = get_object_or_404(RocketGame.objects.select_related("created_by"), pk=game_id)
    if not game.players.filter(user=request.user).exists():
        count = game.players.count()
        can_join = game.status == RocketGame.Status.EN_ATTENTE and count < game.max_players
        return render(
            request,
            "join_invitation.html",
            {
                "mode_name": "Infiltration Rocket",
                "mode_kicker": "Rôles cachés · nuit · débat · vote",
                "host_name": game.created_by.get_username(),
                "player_count": count,
                "max_players": game.max_players,
                "can_join": can_join,
                "join_url": reverse("rocket:join_game", kwargs={"game_id": game.id}),
                "lobby_url": reverse("rocket:lobby"),
            },
            status=200 if can_join else 403,
        )
    advance_if_expired(game.id)
    game.refresh_from_db()
    return render(
        request,
        "rocket/detail.html",
        {"game": game, "game_state": serialize_game_state(game, request.user)},
    )


@login_required
@require_GET
def api_state(request, game_id):
    game = get_object_or_404(RocketGame, pk=game_id)
    advance_if_expired(game.id)
    game.refresh_from_db()
    try:
        state = serialize_game_state(game, request.user)
    except RocketPermissionError as exc:
        return JsonResponse({"error": str(exc)}, status=403)
    return JsonResponse(state)


def _action_view(request, game_id, operation):
    game = get_object_or_404(RocketGame, pk=game_id)
    payload, error = _json_payload(request)
    if error:
        return error
    try:
        operation(game.id, request.user, payload)
    except RocketError as exc:
        return _error_response(exc, game, request.user)
    game.refresh_from_db()
    return JsonResponse({"state": serialize_game_state(game, request.user)})


@login_required
@require_POST
def api_night_action(request, game_id):
    return _action_view(
        request,
        game_id,
        lambda current_id, user, payload: submit_night_action(
            current_id,
            user,
            payload.get("target_id"),
            payload.get("expected_turn_revision"),
        ),
    )


@login_required
@require_POST
def api_start_vote(request, game_id):
    return _action_view(
        request,
        game_id,
        lambda current_id, user, payload: start_vote(
            current_id,
            user,
            payload.get("expected_turn_revision"),
        ),
    )


@login_required
@require_POST
def api_vote(request, game_id):
    return _action_view(
        request,
        game_id,
        lambda current_id, user, payload: submit_vote(
            current_id,
            user,
            payload.get("target_id"),
            payload.get("expected_turn_revision"),
        ),
    )


@login_required
@require_POST
def api_message(request, game_id):
    return _action_view(
        request,
        game_id,
        lambda current_id, user, payload: send_message(
            current_id,
            user,
            payload.get("body"),
            payload.get("expected_turn_revision"),
        ),
    )
