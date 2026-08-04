import json
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from silhouette.models import SilhouetteGame, SilhouetteRound
from silhouette.services import (
    SilhouetteError,
    SilhouettePermissionError,
    StaleRevisionError,
    advance_if_needed,
    create_game,
    get_lobby_state,
    join_game,
    serialize_game_state,
    start_game,
    submit_guess,
)

IMAGE_CACHE_SECONDS = 60 * 60 * 24


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
    status = 403 if isinstance(exc, SilhouettePermissionError) else 400
    return JsonResponse({"error": str(exc)}, status=status)


@login_required
def lobby(request):
    my_games = (
        SilhouetteGame.objects.filter(players__user=request.user)
        .exclude(status=SilhouetteGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .distinct()
    )
    return render(
        request,
        "silhouette/lobby.html",
        {
            "lobby_state": get_lobby_state(request.user),
            "my_games": my_games,
            "round_choices": SilhouetteGame.RoundCount.choices,
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
        round_count = int(request.POST.get("round_count", SilhouetteGame.RoundCount.NORMALE))
    except (TypeError, ValueError):
        round_count = 0
    try:
        game = create_game(request.user, round_count)
    except SilhouetteError as exc:
        messages.error(request, str(exc))
        return redirect("silhouette:lobby")
    return redirect("silhouette:game_detail", game_id=game.id)


@login_required
@require_POST
def join_game_view(request, game_id):
    try:
        join_game(game_id, request.user)
    except SilhouetteGame.DoesNotExist:
        messages.error(request, "Cette partie n'existe plus.")
        return redirect("silhouette:lobby")
    except SilhouetteError as exc:
        messages.error(request, str(exc))
    return redirect("silhouette:game_detail", game_id=game_id)


@login_required
@require_POST
def start_game_view(request, game_id):
    try:
        start_game(game_id, request.user)
    except SilhouetteError as exc:
        messages.error(request, str(exc))
    return redirect("silhouette:game_detail", game_id=game_id)


@login_required
def game_detail(request, game_id):
    game = get_object_or_404(SilhouetteGame, pk=game_id)
    if not game.players.filter(user=request.user).exists():
        can_join = game.status == SilhouetteGame.Status.EN_ATTENTE
        return render(
            request,
            "join_invitation.html",
            {
                "mode_name": "Qui est ce Pokémon ?",
                "mode_kicker": "Silhouette · indices · rapidité",
                "host_name": game.created_by.get_username(),
                "player_count": game.players.count(),
                "max_players": "∞",
                "can_join": can_join,
                "join_url": reverse("silhouette:join_game", kwargs={"game_id": game.id}),
                "lobby_url": reverse("silhouette:lobby"),
            },
            status=200 if can_join else 403,
        )

    advance_if_needed(game.id)
    game.refresh_from_db()
    return render(
        request,
        "silhouette/detail.html",
        {"game": game, "game_state": serialize_game_state(game, request.user)},
    )


@login_required
@require_GET
def api_state(request, game_id):
    game = get_object_or_404(SilhouetteGame, pk=game_id)
    if not game.players.filter(user=request.user).exists():
        return JsonResponse({"error": "Vous ne participez pas à cette partie."}, status=403)
    advance_if_needed(game.id)
    game.refresh_from_db()
    return JsonResponse(serialize_game_state(game, request.user))


@login_required
@require_POST
def api_guess(request, game_id):
    game = get_object_or_404(SilhouetteGame, pk=game_id)
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
    except SilhouetteError as exc:
        return _error_response(exc, game, request.user)

    advance_if_needed(game.id)
    game.refresh_from_db()
    return JsonResponse({**result, "state": serialize_game_state(game, request.user)})


@login_required
@require_GET
def round_image(request, round_id):
    """Sert l'illustration de la manche sans jamais exposer le Pokédex ID.

    Tant que la manche n'est pas révélée, l'image renvoyée est une véritable
    silhouette calculée côté serveur : contrairement à un filtre CSS, elle ne
    peut pas être retirée depuis le navigateur.
    """

    round_obj = get_object_or_404(SilhouetteRound.objects.select_related("pokemon_card", "game"), pk=round_id)
    if not round_obj.game.players.filter(user=request.user).exists():
        return JsonResponse({"error": "Vous ne participez pas à cette partie."}, status=403)

    revealed = round_obj.revealed_at is not None
    content = _artwork_bytes(round_obj.pokemon_card, silhouette=not revealed)
    if content is None:
        return JsonResponse({"error": "Illustration indisponible."}, status=502)

    response = HttpResponse(content, content_type="image/png")
    # Jamais de cache navigateur : la même URL renvoie la silhouette puis la
    # révélation, et un cache partagé ferait fuiter la réponse.
    response["Cache-Control"] = "private, no-store"
    return response


def _artwork_bytes(pokemon_card, *, silhouette: bool):
    cache_key = f"silhouette:artwork:{pokemon_card.pokedex_id}:{'mask' if silhouette else 'full'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    import requests

    try:
        response = requests.get(pokemon_card.sprite_url, timeout=10)
        response.raise_for_status()
        original = response.content
    except requests.RequestException:
        return None

    content = _to_silhouette(original) if silhouette else original
    if content is None:
        return None
    cache.set(cache_key, content, IMAGE_CACHE_SECONDS)
    return content


def _to_silhouette(image_bytes):
    """Noircit tous les pixels visibles en conservant la transparence."""

    from PIL import Image

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            black = Image.new("RGBA", rgba.size, (12, 20, 34, 255))
            black.putalpha(alpha)
            buffer = BytesIO()
            black.save(buffer, format="PNG")
            return buffer.getvalue()
    except OSError:
        return None
