import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import GuessWhoGame
from .services import (
    GuessWhoError,
    GuessWhoPermissionError,
    StaleRevisionError,
    answer_question,
    ask_question,
    choose_target,
    get_lobby_state,
    guess_pokemon,
    reset_candidates,
    serialize_game_state,
    toggle_candidate,
)
from .services import (
    create_game as create_game_service,
)
from .services import (
    join_game as join_game_service,
)


def _read_json_object(request):
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "Requête JSON invalide."}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse(
            {"error": "La requête doit contenir un objet JSON."},
            status=400,
        )
    return payload, None


def _read_expected_revision(payload):
    revision = payload.get("expected_turn_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return None, JsonResponse(
            {"error": "Révision de tour invalide."},
            status=400,
        )
    return revision, None


def _read_positive_int(payload, key, error_message):
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None, JsonResponse({"error": error_message}, status=400)
    return value, None


def _error_response(exc, game_id, user):
    if isinstance(exc, StaleRevisionError):
        game = get_object_or_404(GuessWhoGame, pk=game_id)
        return JsonResponse(
            {
                "error": str(exc),
                "code": "stale_revision",
                "state": serialize_game_state(game, user),
            },
            status=409,
        )
    status = 403 if isinstance(exc, GuessWhoPermissionError) else 400
    return JsonResponse({"error": str(exc)}, status=status)


@login_required
def lobby(request):
    open_games = (
        GuessWhoGame.objects.filter(status=GuessWhoGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
    )
    my_games = (
        GuessWhoGame.objects.annotate(player_count=Count("players"))
        .filter(players__user=request.user)
        .select_related("created_by", "winner__user")
        .distinct()
    )
    return render(
        request,
        "guesswho/lobby.html",
        {
            "open_games": open_games,
            "my_games": my_games,
            "lobby_state": get_lobby_state(request.user),
        },
    )


@login_required
@require_GET
def api_lobby_state(request):
    return JsonResponse(get_lobby_state(request.user))


@login_required
@require_POST
def create_game(request):
    try:
        game = create_game_service(request.user)
    except GuessWhoError as exc:
        messages.error(request, str(exc))
        return redirect("guesswho:lobby")
    return redirect("guesswho:game_detail", game_id=game.id)


@login_required
@require_POST
def join_game(request, game_id):
    try:
        game, _player = join_game_service(game_id, request.user)
    except GuessWhoGame.DoesNotExist:
        game = get_object_or_404(GuessWhoGame, pk=game_id)
        return redirect("guesswho:game_detail", game_id=game.id)
    except GuessWhoError as exc:
        messages.error(request, str(exc))
        return redirect("guesswho:lobby")
    return redirect("guesswho:game_detail", game_id=game.id)


@login_required
def game_detail(request, game_id):
    game = get_object_or_404(GuessWhoGame, pk=game_id)
    if not game.players.filter(user=request.user).exists():
        player_count = game.players.count()
        can_join = game.status == GuessWhoGame.Status.EN_ATTENTE and player_count < game.max_players
        return render(
            request,
            "join_invitation.html",
            {
                "mode_name": "Qui est-ce ? Pokémon",
                "mode_kicker": "Déduction · questions · duel",
                "host_name": game.created_by.get_username(),
                "player_count": player_count,
                "max_players": game.max_players,
                "can_join": can_join,
                "join_url": reverse("guesswho:join_game", kwargs={"game_id": game.id}),
                "lobby_url": reverse("guesswho:lobby"),
            },
            status=200 if can_join else 403,
        )
    return render(
        request,
        "guesswho/detail.html",
        {"game": game, "game_state": serialize_game_state(game, request.user)},
    )


@login_required
@require_GET
def api_state(request, game_id):
    game = get_object_or_404(GuessWhoGame, pk=game_id)
    try:
        state = serialize_game_state(game, request.user)
    except GuessWhoPermissionError as exc:
        return JsonResponse({"error": str(exc)}, status=403)
    return JsonResponse(state)


@login_required
@require_POST
def api_choose_target(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_expected_revision(payload)
    if error:
        return error
    card_id, error = _read_positive_int(payload, "pokemon_card_id", "Pokémon invalide.")
    if error:
        return error
    try:
        game = choose_target(game_id, request.user, card_id, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except GuessWhoGame.DoesNotExist:
        get_object_or_404(GuessWhoGame, pk=game_id)
    except GuessWhoError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_ask_question(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_expected_revision(payload)
    if error:
        return error
    try:
        game = ask_question(game_id, request.user, payload.get("question"), revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except GuessWhoGame.DoesNotExist:
        get_object_or_404(GuessWhoGame, pk=game_id)
    except GuessWhoError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_answer_question(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_expected_revision(payload)
    if error:
        return error
    answer = payload.get("answer")
    if not isinstance(answer, bool):
        return JsonResponse({"error": "La réponse doit être Oui ou Non."}, status=400)
    try:
        game = answer_question(game_id, request.user, answer, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except GuessWhoGame.DoesNotExist:
        get_object_or_404(GuessWhoGame, pk=game_id)
    except GuessWhoError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_guess(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_expected_revision(payload)
    if error:
        return error
    card_id, error = _read_positive_int(payload, "pokemon_card_id", "Pokémon invalide.")
    if error:
        return error
    try:
        game = guess_pokemon(game_id, request.user, card_id, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except GuessWhoGame.DoesNotExist:
        get_object_or_404(GuessWhoGame, pk=game_id)
    except GuessWhoError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_reset_candidates(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_expected_revision(payload)
    if error:
        return error
    try:
        game = reset_candidates(game_id, request.user, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except GuessWhoGame.DoesNotExist:
        get_object_or_404(GuessWhoGame, pk=game_id)
    except GuessWhoError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_toggle_candidate(request, game_id, pokemon_card_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_expected_revision(payload)
    if error:
        return error
    is_eliminated = payload.get("is_eliminated")
    if not isinstance(is_eliminated, bool):
        return JsonResponse({"error": "État de carte invalide."}, status=400)
    try:
        game = toggle_candidate(
            game_id,
            request.user,
            pokemon_card_id,
            is_eliminated,
            revision,
        )
        return JsonResponse(serialize_game_state(game, request.user))
    except GuessWhoGame.DoesNotExist:
        get_object_or_404(GuessWhoGame, pk=game_id)
    except GuessWhoError as exc:
        return _error_response(exc, game_id, request.user)
