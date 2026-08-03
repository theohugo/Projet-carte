from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from game.api import get_lobby_state, invalidate_game_state_cache
from game.forms import SignUpForm
from game.game_engine import GameEngine, GameEngineError
from game.models import Game, GameCard, PokemonType

OPPONENT_CARD_BACK_LIMIT = 10


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("lobby")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
def lobby(request):
    if request.method == "POST":
        game = Game.objects.create(created_by=request.user)
        GameEngine(game).add_player(request.user)
        return redirect("game_detail", game_id=game.id)

    open_games = Game.objects.filter(status=Game.Status.EN_ATTENTE).select_related("created_by")
    my_games = Game.objects.filter(players__user=request.user).exclude(status=Game.Status.EN_ATTENTE)
    return render(
        request,
        "game/lobby.html",
        {"open_games": open_games, "my_games": my_games, "lobby_state": get_lobby_state(request.user)},
    )


@login_required
@require_POST
@transaction.atomic
def join_game(request, game_id):
    game = get_object_or_404(Game.objects.select_for_update(), pk=game_id)
    try:
        GameEngine(game).add_player(request.user)
    except GameEngineError as exc:
        messages.error(request, str(exc))
        return redirect("lobby")
    invalidate_game_state_cache(game)
    return redirect("game_detail", game_id=game.id)


@login_required
@require_POST
@transaction.atomic
def start_game_view(request, game_id):
    game = get_object_or_404(Game.objects.select_for_update(), pk=game_id)
    if game.created_by_id != request.user.id:
        return HttpResponseForbidden("Seul le créateur de la partie peut la démarrer.")
    try:
        GameEngine(game).start_game()
    except GameEngineError as exc:
        messages.error(request, str(exc))
    invalidate_game_state_cache(game)
    return redirect("game_detail", game_id=game.id)


@login_required
def game_detail(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game_player = game.players.filter(user=request.user).first()
    if game_player is None:
        return HttpResponseForbidden("Vous ne participez pas à cette partie.")
    game_state = GameEngine(game).get_game_state(for_player=game_player)
    players_state = game_state["players"]
    my_index = next(index for index, player in enumerate(players_state) if "hand" in player)
    my_player = players_state[my_index]
    seat_order = players_state[my_index + 1 :] + players_state[:my_index]
    opponents = [
        {
            **player,
            "card_back_slots": range(min(player["hand_count"], OPPONENT_CARD_BACK_LIMIT)),
            "hidden_card_count": max(0, player["hand_count"] - OPPONENT_CARD_BACK_LIMIT),
        }
        for player in seat_order
        if "hand" not in player
    ]
    if game.status == Game.Status.EN_COURS:
        engine = GameEngine(game)
        hand_cards = GameCard.objects.select_related("pokemon_card").filter(
            game=game, location=GameCard.Location.MAIN, owner=game_player
        )
        playable_by_id = {
            game_card.id: engine.is_move_valid(game_player, game_card)[0] for game_card in hand_cards
        }
        for card in my_player["hand"]:
            card["is_playable"] = playable_by_id[card["id"]]
    return render(
        request,
        "game/detail.html",
        {
            "game": game,
            "is_creator": game.created_by_id == request.user.id,
            "players": game.players.select_related("user").all(),
            "game_state": game_state,
            "my_player": my_player,
            "opponents": opponents,
            "declared_types": PokemonType.objects.order_by("name_fr"),
        },
    )
