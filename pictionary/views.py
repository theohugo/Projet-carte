import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from pictionary.models import PictionaryGame
from pictionary.services import (
    PictionaryError,
    PictionaryPermissionError,
    StaleRevisionError,
    add_stroke,
    advance_if_needed,
    create_game,
    get_lobby_state,
    join_game,
    serialize_game_state,
    start_game,
    submit_guess,
)


def _read_json_object(request):
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "Requête JSON invalide."}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "La requête doit contenir un objet JSON."}, status=400)
    return payload, None


def _error_response(exc, game, user):
    if isinstance(exc, StaleRevisionError):
        return JsonResponse(
            {"error": str(exc), "code": "stale_revision", "state": serialize_game_state(game, user)},
            status=409,
        )
    status = 403 if isinstance(exc, PictionaryPermissionError) else 400
    return JsonResponse({"error": str(exc)}, status=status)


def _since_sequence(request):
    try:
        return max(0, int(request.GET.get("since", 0)))
    except (TypeError, ValueError):
        return 0


@login_required
def lobby(request):
    my_games = (
        PictionaryGame.objects.filter(players__user=request.user)
        .exclude(status=PictionaryGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .distinct()
    )
    return render(
        request,
        "pictionary/lobby.html",
        {
            "lobby_state": get_lobby_state(request.user),
            "my_games": my_games,
            "round_choices": PictionaryGame.RoundCount.choices,
        },
    )


@login_required
@require_GET
def api_lobby_state(request):
    return JsonResponse(get_lobby_state(request.user))


@login_required
@require_POST
def create_game_view(request):
    try:
        round_count = int(request.POST.get("round_count", PictionaryGame.RoundCount.NORMALE))
    except (TypeError, ValueError):
        round_count = 0
    try:
        game = create_game(request.user, round_count)
    except PictionaryError as exc:
        messages.error(request, str(exc))
        return redirect("pictionary:lobby")
    return redirect("pictionary:game_detail", game_id=game.id)


@login_required
@require_POST
def join_game_view(request, game_id):
    try:
        join_game(game_id, request.user)
    except PictionaryGame.DoesNotExist:
        messages.error(request, "Cette partie n'existe plus.")
        return redirect("pictionary:lobby")
    except PictionaryError as exc:
        messages.error(request, str(exc))
    return redirect("pictionary:game_detail", game_id=game_id)


@login_required
@require_POST
def start_game_view(request, game_id):
    try:
        start_game(game_id, request.user)
    except PictionaryError as exc:
        messages.error(request, str(exc))
    return redirect("pictionary:game_detail", game_id=game_id)


@login_required
def game_detail(request, game_id):
    game = get_object_or_404(PictionaryGame, pk=game_id)
    if not game.players.filter(user=request.user).exists():
        can_join = game.status == PictionaryGame.Status.EN_ATTENTE
        return render(
            request,
            "join_invitation.html",
            {
                "mode_name": "Pictionary Pokémon",
                "mode_kicker": "Dessin · devinette · rapidité",
                "host_name": game.created_by.get_username(),
                "player_count": game.players.count(),
                "max_players": "∞",
                "can_join": can_join,
                "join_url": reverse("pictionary:join_game", kwargs={"game_id": game.id}),
                "lobby_url": reverse("pictionary:lobby"),
            },
            status=200 if can_join else 403,
        )

    advance_if_needed(game.id)
    game.refresh_from_db()
    return render(
        request,
        "pictionary/detail.html",
        {"game": game, "game_state": serialize_game_state(game, request.user)},
    )


@login_required
@require_GET
def api_state(request, game_id):
    game = get_object_or_404(PictionaryGame, pk=game_id)
    if not game.players.filter(user=request.user).exists():
        return JsonResponse({"error": "Vous ne participez pas à cette partie."}, status=403)
    advance_if_needed(game.id)
    game.refresh_from_db()
    return JsonResponse(serialize_game_state(game, request.user, since_sequence=_since_sequence(request)))


@login_required
@require_POST
def api_stroke(request, game_id):
    game = get_object_or_404(PictionaryGame, pk=game_id)
    payload, error = _read_json_object(request)
    if error:
        return error

    try:
        sequence = add_stroke(game.id, request.user, payload)
    except PictionaryError as exc:
        return _error_response(exc, game, request.user)
    return JsonResponse({"sequence": sequence})


@login_required
@require_POST
def api_guess(request, game_id):
    game = get_object_or_404(PictionaryGame, pk=game_id)
    payload, error = _read_json_object(request)
    if error:
        return error

    expected_revision = payload.get("expected_turn_revision")
    if expected_revision is not None and (
        isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
    ):
        return JsonResponse({"error": "Révision de tour invalide."}, status=400)

    try:
        result = submit_guess(game.id, request.user, payload.get("text"), expected_revision)
    except PictionaryError as exc:
        return _error_response(exc, game, request.user)

    advance_if_needed(game.id)
    game.refresh_from_db()
    return JsonResponse({**result, "state": serialize_game_state(game, request.user)})
