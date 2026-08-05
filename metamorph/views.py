import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from game.guests import guest_action, guest_allowed, public_lobby
from game.models import PokemonCard
from game.pokemon_names import bilingual_text

from .models import MetamorphGame
from .services import (
    MAX_PLAYERS,
    MetamorphError,
    MetamorphPermissionError,
    StaleRevisionError,
    add_bot,
    draw_card,
    get_lobby_state,
    play_bot_turn,
    remove_bot,
    serialize_game_state,
    start_game,
)
from .services import create_game as create_game_service
from .services import join_game as join_game_service


def _read_json_object(request):
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse(
            {"error": bilingual_text("Requête JSON invalide.", "Invalid JSON request.")},
            status=400,
        )
    if not isinstance(payload, dict):
        return None, JsonResponse(
            {
                "error": bilingual_text(
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
            {"error": bilingual_text("Révision de tour invalide.", "Invalid turn revision.")},
            status=400,
        )
    return revision, None


def _error_response(exc, game_id, user):
    if isinstance(exc, StaleRevisionError):
        game = get_object_or_404(MetamorphGame, pk=game_id)
        return JsonResponse(
            {
                "error": str(exc),
                "code": "stale_revision",
                "state": serialize_game_state(game, user),
            },
            status=409,
        )
    status = 403 if isinstance(exc, MetamorphPermissionError) else 400
    return JsonResponse({"error": str(exc)}, status=status)


@public_lobby
def lobby(request):
    open_games = list(
        MetamorphGame.objects.filter(status=MetamorphGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
        .filter(player_count__lt=MAX_PLAYERS)
        .order_by("-created_at")
    )
    my_games = []
    if request.user.is_authenticated:
        my_games = list(
            MetamorphGame.objects.annotate(player_count=Count("players", distinct=True))
            .filter(players__user=request.user)
            .select_related("created_by")
            .distinct()
            .order_by("-created_at")
        )
    return render(
        request,
        "metamorph/lobby.html",
        {
            "open_games": open_games,
            "my_games": my_games,
            "lobby_state": get_lobby_state(request.user),
            "ditto_art": PokemonCard.objects.filter(pokedex_id=132).first(),
        },
    )


@require_GET
def api_lobby_state(request):
    return JsonResponse(get_lobby_state(request.user))


@guest_action
@require_POST
def create_game(request):
    game = create_game_service(request.user)
    return redirect("metamorph:game_detail", game_id=game.id)


@guest_action
@require_POST
def join_game(request, game_id):
    try:
        game, _player = join_game_service(game_id, request.user)
    except MetamorphGame.DoesNotExist:
        get_object_or_404(MetamorphGame, pk=game_id)
    except MetamorphError as exc:
        messages.error(request, str(exc))
        return redirect("metamorph:lobby")
    return redirect("metamorph:game_detail", game_id=game.id)


@guest_allowed
def game_detail(request, game_id):
    game = get_object_or_404(MetamorphGame, pk=game_id)
    if not game.players.filter(user=request.user).exists():
        player_count = game.players.count()
        can_join = game.status == MetamorphGame.Status.EN_ATTENTE and player_count < MAX_PLAYERS
        return render(
            request,
            "join_invitation.html",
            {
                "mode_name": bilingual_text("Métamorph Mystère", "Ditto Mystery"),
                "mode_kicker": bilingual_text(
                    "Paires · bluff · 2 à 6 joueurs",
                    "Pairs · bluffing · 2 to 6 players",
                ),
                "host_name": game.created_by.get_username(),
                "player_count": player_count,
                "max_players": MAX_PLAYERS,
                "can_join": can_join,
                "join_url": reverse("metamorph:join_game", kwargs={"game_id": game.id}),
                "lobby_url": reverse("metamorph:lobby"),
            },
            status=200 if can_join else 403,
        )
    return render(
        request,
        "metamorph/detail.html",
        {
            "game": game,
            "game_state": serialize_game_state(game, request.user),
        },
    )


@login_required
@require_GET
def api_state(request, game_id):
    game = get_object_or_404(MetamorphGame, pk=game_id)
    try:
        return JsonResponse(serialize_game_state(game, request.user))
    except MetamorphPermissionError as exc:
        return JsonResponse({"error": str(exc)}, status=403)


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
        game = start_game(game_id, request.user, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except MetamorphGame.DoesNotExist:
        get_object_or_404(MetamorphGame, pk=game_id)
    except MetamorphError as exc:
        return _error_response(exc, game_id, request.user)


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
    except MetamorphGame.DoesNotExist:
        get_object_or_404(MetamorphGame, pk=game_id)
    except MetamorphError as exc:
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
    except MetamorphGame.DoesNotExist:
        get_object_or_404(MetamorphGame, pk=game_id)
    except MetamorphError as exc:
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
        game = play_bot_turn(game_id, request.user, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except MetamorphGame.DoesNotExist:
        get_object_or_404(MetamorphGame, pk=game_id)
    except MetamorphError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_draw(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_revision(payload)
    if error:
        return error
    card_position = payload.get("card_position")
    if isinstance(card_position, bool) or not isinstance(card_position, int) or card_position <= 0:
        return JsonResponse(
            {"error": bilingual_text("Carte face cachée invalide.", "Invalid face-down card.")},
            status=400,
        )
    try:
        game = draw_card(
            game_id,
            request.user,
            card_position,
            revision,
        )
        return JsonResponse(serialize_game_state(game, request.user))
    except MetamorphGame.DoesNotExist:
        get_object_or_404(MetamorphGame, pk=game_id)
    except MetamorphError as exc:
        return _error_response(exc, game_id, request.user)
