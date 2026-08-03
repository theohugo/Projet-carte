import json

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from game.game_engine import GameEngine, GameEngineError
from game.models import Game, GameCard, PokemonType

STATE_CACHE_TIMEOUT = 2  # secondes — amortit le polling front sans jamais servir un état obsolète longtemps.


def _get_game_player_or_403(game, user):
    return game.players.filter(user=user).first()


@login_required
@require_GET
def api_game_state(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game_player = _get_game_player_or_403(game, request.user)
    if game_player is None:
        return JsonResponse({"error": "Vous ne participez pas à cette partie."}, status=403)

    cache_key = f"game:{game.id}:state:{game_player.id}"
    state = cache.get(cache_key)
    if state is None:
        state = GameEngine(game).get_game_state(for_player=game_player)
        cache.set(cache_key, state, timeout=STATE_CACHE_TIMEOUT)
    return JsonResponse(state)


@login_required
@require_POST
def api_play_card(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game_player = _get_game_player_or_403(game, request.user)
    if game_player is None:
        return JsonResponse({"error": "Vous ne participez pas à cette partie."}, status=403)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Requête invalide."}, status=400)

    game_card = GameCard.objects.filter(pk=payload.get("game_card_id"), game=game).first()
    if game_card is None:
        return JsonResponse({"error": "Carte introuvable."}, status=400)

    declared_type = None
    declared_type_slug = payload.get("declared_type")
    if declared_type_slug:
        declared_type = PokemonType.objects.filter(slug=declared_type_slug).first()

    engine = GameEngine(game)
    try:
        engine.play_card(game_player, game_card, declared_type=declared_type)
    except GameEngineError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(engine.get_game_state(for_player=game_player))


@login_required
@require_POST
def api_draw_card(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game_player = _get_game_player_or_403(game, request.user)
    if game_player is None:
        return JsonResponse({"error": "Vous ne participez pas à cette partie."}, status=403)

    engine = GameEngine(game)
    try:
        engine.draw_card(game_player)
    except GameEngineError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(engine.get_game_state(for_player=game_player))
