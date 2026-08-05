import json

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import get_language
from django.views.decorators.http import require_GET, require_POST

from game.bot_player import perform_bot_turn
from game.game_engine import GameEngine, GameEngineError, close_stale_games
from game.models import Game, GameCard
from game.pokemon_names import bilingual_text

STATE_CACHE_TIMEOUT = 2  # secondes — amortit le polling front sans jamais servir un état obsolète longtemps.


def get_lobby_state(user):
    """Empreinte légère du lobby pour détecter les nouvelles parties sans F5."""
    close_stale_games()
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    return {
        "open_games": [
            {
                "id": str(game["id"]),
                "player_count": game["player_count"],
                "max_players": game["max_players"],
            }
            for game in Game.objects.filter(status=Game.Status.EN_ATTENTE)
            .annotate(player_count=models.Count("players"))
            .order_by("-created_at")
            .values("id", "player_count", "max_players")
        ],
        "my_game_ids": (
            [
                str(game_id)
                for game_id in Game.objects.filter(players__user=user)
                .exclude(status=Game.Status.EN_ATTENTE)
                .order_by("-created_at")
                .values_list("id", flat=True)
            ]
            if is_authenticated
            else []
        ),
    }


def _get_game_player_or_403(game, user):
    return game.players.filter(user=user).first()


def _state_cache_key(game_id, game_player_id, language=None):
    language = (language or get_language() or "fr").split("-", 1)[0]
    return f"game:{game_id}:state:{game_player_id}:{language}"


def invalidate_game_state_cache(game):
    """À appeler après toute action qui change l'état de la partie : sans ça,
    un joueur peut recevoir jusqu'à STATE_CACHE_TIMEOUT secondes de données
    périmées (carte encore en main, défausse pas à jour...) au prochain poll,
    y compris juste après avoir joué lui-même son propre coup."""
    keys = [
        _state_cache_key(game.id, gp_id, language)
        for gp_id in game.players.values_list("id", flat=True)
        for language in ("fr", "en")
    ]
    transaction.on_commit(lambda: cache.delete_many(keys))


@login_required
@require_GET
def api_game_state(request, game_id):
    close_stale_games()
    game = get_object_or_404(Game, pk=game_id)
    game_player = _get_game_player_or_403(game, request.user)
    if game_player is None:
        return JsonResponse(
            {"error": bilingual_text("Vous ne participez pas à cette partie.", "You are not in this game.")},
            status=403,
        )

    cache_key = _state_cache_key(game.id, game_player.id)
    state = cache.get(cache_key)
    if state is None:
        state = GameEngine(game).get_game_state(for_player=game_player)
        cache.set(cache_key, state, timeout=STATE_CACHE_TIMEOUT)
    return JsonResponse(state)


@require_GET
def api_lobby_state(request):
    return JsonResponse(get_lobby_state(request.user))


@login_required
@require_POST
@transaction.atomic
def api_start_game(request, game_id):
    game = get_object_or_404(Game.objects.select_for_update(), pk=game_id)
    game_player = _get_game_player_or_403(game, request.user)
    if game_player is None:
        return JsonResponse(
            {"error": bilingual_text("Vous ne participez pas à cette partie.", "You are not in this game.")},
            status=403,
        )
    if game.created_by_id != request.user.id:
        return JsonResponse(
            {
                "error": bilingual_text(
                    "Seul le créateur de la partie peut la démarrer.",
                    "Only the room host can start the game.",
                )
            },
            status=403,
        )

    engine = GameEngine(game)
    try:
        engine.start_game()
    except GameEngineError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    invalidate_game_state_cache(game)
    return JsonResponse(engine.get_game_state(for_player=game_player))


@login_required
@require_POST
@transaction.atomic
def api_play_card(request, game_id):
    # Verrouille la partie pendant tout le coup : deux onglets (ou deux clics
    # très rapides) ne peuvent pas jouer deux cartes sur le même tour.
    game = get_object_or_404(Game.objects.select_for_update(), pk=game_id)
    game_player = _get_game_player_or_403(game, request.user)
    if game_player is None:
        return JsonResponse(
            {"error": bilingual_text("Vous ne participez pas à cette partie.", "You are not in this game.")},
            status=403,
        )

    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": bilingual_text("Requête invalide.", "Invalid request.")}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse(
            {
                "error": bilingual_text(
                    "La requête doit être un objet JSON.", "The request must be a JSON object."
                )
            },
            status=400,
        )

    declared_type = payload.get("declared_type")
    if declared_type is not None and not isinstance(declared_type, str):
        return JsonResponse(
            {"error": bilingual_text("Type déclaré invalide.", "Invalid declared type.")}, status=400
        )

    game_card_id = payload.get("game_card_id")
    if isinstance(game_card_id, bool) or not isinstance(game_card_id, int) or game_card_id <= 0:
        return JsonResponse(
            {"error": bilingual_text("Identifiant de carte invalide.", "Invalid card identifier.")},
            status=400,
        )

    game_card = GameCard.objects.filter(pk=game_card_id, game=game).first()
    if game_card is None:
        return JsonResponse({"error": bilingual_text("Carte introuvable.", "Card not found.")}, status=400)

    engine = GameEngine(game)
    try:
        engine.play_card(game_player, game_card, declared_type_slug=declared_type)
    except GameEngineError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    invalidate_game_state_cache(game)
    return JsonResponse(engine.get_game_state(for_player=game_player))


@login_required
@require_POST
@transaction.atomic
def api_bot_turn(request, game_id):
    """Joue au plus un tour IA, de façon idempotente entre plusieurs clients."""
    game = get_object_or_404(Game.objects.select_for_update(), pk=game_id)
    game_player = _get_game_player_or_403(game, request.user)
    if game_player is None:
        return JsonResponse(
            {"error": bilingual_text("Vous ne participez pas à cette partie.", "You are not in this game.")},
            status=403,
        )

    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": bilingual_text("Révision de tour invalide.", "Invalid turn revision.")}, status=400
        )
    expected_revision = payload.get("expected_turn_revision") if isinstance(payload, dict) else None
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
        return JsonResponse(
            {"error": bilingual_text("Révision de tour invalide.", "Invalid turn revision.")}, status=400
        )

    engine = GameEngine(game)
    if expected_revision != game.turn_revision or game.status != Game.Status.EN_COURS:
        return JsonResponse(engine.get_game_state(for_player=game_player))

    current_player = engine.get_current_player()
    if not current_player.is_bot:
        return JsonResponse(engine.get_game_state(for_player=game_player))

    try:
        perform_bot_turn(engine)
    except GameEngineError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    invalidate_game_state_cache(game)
    return JsonResponse(engine.get_game_state(for_player=game_player))


@login_required
@require_POST
@transaction.atomic
def api_draw_card(request, game_id):
    game = get_object_or_404(Game.objects.select_for_update(), pk=game_id)
    game_player = _get_game_player_or_403(game, request.user)
    if game_player is None:
        return JsonResponse(
            {"error": bilingual_text("Vous ne participez pas à cette partie.", "You are not in this game.")},
            status=403,
        )

    engine = GameEngine(game)
    try:
        engine.draw_card(game_player)
    except GameEngineError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    invalidate_game_state_cache(game)
    return JsonResponse(engine.get_game_state(for_player=game_player))
