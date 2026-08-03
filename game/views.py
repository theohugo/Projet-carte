from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from game.forms import SignUpForm
from game.game_engine import GameEngine, GameEngineError
from game.models import Game


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
    return render(request, "game/lobby.html", {"open_games": open_games, "my_games": my_games})


@login_required
@require_POST
def join_game(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    try:
        GameEngine(game).add_player(request.user)
    except GameEngineError as exc:
        messages.error(request, str(exc))
        return redirect("lobby")
    return redirect("game_detail", game_id=game.id)


@login_required
@require_POST
def start_game_view(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    if game.created_by_id != request.user.id:
        return HttpResponseForbidden("Seul le créateur de la partie peut la démarrer.")
    try:
        GameEngine(game).start_game()
    except GameEngineError as exc:
        messages.error(request, str(exc))
    return redirect("game_detail", game_id=game.id)


@login_required
def game_detail(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game_player = game.players.filter(user=request.user).first()
    if game_player is None:
        return HttpResponseForbidden("Vous ne participez pas à cette partie.")
    return render(
        request,
        "game/detail.html",
        {
            "game": game,
            "is_creator": game.created_by_id == request.user.id,
            "player_count": game.players.count(),
        },
    )
