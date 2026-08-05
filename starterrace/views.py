import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from game.guests import guest_action, guest_allowed, public_lobby

from .i18n import javascript_catalog, pokemon_name, text
from .models import Game, Pawn
from .services import (
    MAX_PLAYERS,
    StaleRevisionError,
    StarterRaceError,
    StarterRacePermissionError,
    add_bot,
    advance_bot_step,
    create_game,
    get_lobby_state,
    get_starter_cards,
    join_game,
    move_pawn,
    remove_bot,
    roll_dice,
    serialize_game_state,
    start_game,
)


def _read_json_object(request):
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse(
            {"error": text("Requête JSON invalide.", "Invalid JSON request.")}, status=400
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


def _read_expected_revision(payload):
    revision = payload.get("expected_turn_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return None, JsonResponse(
            {"error": text("Révision de tour invalide.", "Invalid turn revision.")}, status=400
        )
    return revision, None


def _read_pawn_id(payload):
    pawn_id = payload.get("pawn_id")
    if isinstance(pawn_id, bool) or not isinstance(pawn_id, int) or pawn_id <= 0:
        return None, JsonResponse({"error": text("Pion invalide.", "Invalid pawn.")}, status=400)
    return pawn_id, None


def _error_response(exc, game_id, user):
    if isinstance(exc, StaleRevisionError):
        game = get_object_or_404(Game, pk=game_id)
        return JsonResponse(
            {
                "error": str(exc),
                "code": "stale_revision",
                "state": serialize_game_state(game, user),
            },
            status=409,
        )
    status = 403 if isinstance(exc, StarterRacePermissionError) else 400
    return JsonResponse({"error": str(exc)}, status=status)


@public_lobby
def lobby(request):
    starter_cards = [
        {"name": pokemon_name(card), "sprite_url": card.sprite_url} for card in get_starter_cards()
    ]
    return render(
        request,
        "starterrace/lobby.html",
        {
            "lobby_state": get_lobby_state(request.user),
            "starter_cards": starter_cards,
        },
    )


@require_GET
def api_lobby_state(request):
    return JsonResponse(get_lobby_state(request.user))


@guest_action
@require_POST
def create_game_view(request):
    try:
        game = create_game(request.user)
    except StarterRaceError as exc:
        messages.error(request, str(exc))
        return redirect("starterrace:lobby")
    return redirect("starterrace:game_detail", game_id=game.id)


@guest_action
@require_POST
def join_game_view(request, game_id):
    try:
        game, _player = join_game(game_id, request.user)
    except Game.DoesNotExist:
        messages.error(
            request,
            text("Cette course n'existe plus.", "This race no longer exists."),
        )
        return redirect("starterrace:lobby")
    except StarterRaceError as exc:
        messages.error(request, str(exc))
        return redirect("starterrace:lobby")
    return redirect("starterrace:game_detail", game_id=game.id)


@login_required
@require_POST
def add_bot_view(request, game_id):
    try:
        game, bot = add_bot(game_id, request.user)
    except Game.DoesNotExist:
        messages.error(
            request,
            text("Cette course n'existe plus.", "This race no longer exists."),
        )
        return redirect("starterrace:lobby")
    except StarterRaceError as exc:
        messages.error(request, str(exc))
        return redirect("starterrace:game_detail", game_id=game_id)
    messages.success(
        request,
        text("%(bot)s rejoint la course.", "%(bot)s joined the race.") % {"bot": bot.display_name},
    )
    return redirect("starterrace:game_detail", game_id=game.id)


@login_required
@require_POST
def remove_bot_view(request, game_id, player_id):
    try:
        game = remove_bot(game_id, request.user, player_id)
    except Game.DoesNotExist:
        messages.error(
            request,
            text("Cette course n'existe plus.", "This race no longer exists."),
        )
        return redirect("starterrace:lobby")
    except StarterRaceError as exc:
        messages.error(request, str(exc))
        return redirect("starterrace:game_detail", game_id=game_id)
    messages.success(request, text("Le bot a été retiré.", "The bot was removed."))
    return redirect("starterrace:game_detail", game_id=game.id)


@login_required
@require_POST
def start_game_view(request, game_id):
    try:
        start_game(game_id, request.user)
    except Game.DoesNotExist:
        messages.error(
            request,
            text("Cette course n'existe plus.", "This race no longer exists."),
        )
        return redirect("starterrace:lobby")
    except StarterRaceError as exc:
        messages.error(request, str(exc))
    return redirect("starterrace:game_detail", game_id=game_id)


@guest_allowed
def game_detail(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    if not game.players.filter(user=request.user).exists():
        player_count = game.players.count()
        can_join = game.status == Game.Status.EN_ATTENTE and player_count < MAX_PLAYERS
        return render(
            request,
            "join_invitation.html",
            {
                "mode_name": text("Course des Starters", "Starter Race"),
                "mode_kicker": text(
                    "Dés · raccourcis · Ligue Pokémon",
                    "Dice · shortcuts · Pokémon League",
                ),
                "host_name": game.created_by.get_username(),
                "player_count": player_count,
                "max_players": MAX_PLAYERS,
                "can_join": can_join,
                "join_url": reverse("starterrace:join_game", kwargs={"game_id": game.id}),
                "lobby_url": reverse("starterrace:lobby"),
            },
            status=200 if can_join else 403,
        )
    return render(
        request,
        "starterrace/detail.html",
        {
            "game": game,
            "game_state": serialize_game_state(game, request.user),
            "ui_i18n": javascript_catalog(),
        },
    )


@login_required
@require_GET
def api_state(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    try:
        if game.players.filter(user=request.user).exists():
            # Une seule étape d'IA par synchronisation permet au navigateur
            # de montrer le lancer puis le déplacement, sans sauter des coups.
            game = advance_bot_step(game.id)
        return JsonResponse(serialize_game_state(game, request.user))
    except StarterRacePermissionError as exc:
        return JsonResponse({"error": str(exc)}, status=403)


@login_required
@require_POST
def api_roll(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_expected_revision(payload)
    if error:
        return error
    try:
        game = roll_dice(game_id, request.user, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except Game.DoesNotExist:
        get_object_or_404(Game, pk=game_id)
    except StarterRaceError as exc:
        return _error_response(exc, game_id, request.user)


@login_required
@require_POST
def api_move(request, game_id):
    payload, error = _read_json_object(request)
    if error:
        return error
    revision, error = _read_expected_revision(payload)
    if error:
        return error
    pawn_id, error = _read_pawn_id(payload)
    if error:
        return error
    try:
        game = move_pawn(game_id, request.user, pawn_id, revision)
        return JsonResponse(serialize_game_state(game, request.user))
    except (Game.DoesNotExist, Pawn.DoesNotExist):
        get_object_or_404(Game, pk=game_id)
    except StarterRaceError as exc:
        return _error_response(exc, game_id, request.user)
