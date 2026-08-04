from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from game.api import get_lobby_state, invalidate_game_state_cache
from game.forms import AccountForm, ProfileForm, SignUpForm
from game.game_engine import GameEngine, GameEngineError, close_stale_games
from game.models import Friendship, Game, GameCard, Profile
from game.pokemon_types import POKEMON_TYPES

OPPONENT_CARD_BACK_LIMIT = 10


def _friendship_pair_key(first_user, second_user):
    """Construit une clé unique commune aux deux utilisateurs."""

    first_id, second_id = sorted(
        (
            first_user.pk,
            second_user.pk,
        )
    )

    return f"{first_id}:{second_id}"


def _get_relationship(current_user, other_user):
    """Retourne la relation existante et son état pour l'interface."""

    if current_user.pk == other_user.pk:
        return None, "self"

    friendship = Friendship.objects.filter(
        pair_key=_friendship_pair_key(
            current_user,
            other_user,
        )
    ).first()

    if friendship is None or friendship.status == Friendship.Status.REJECTED:
        return friendship, "none"

    if friendship.status == Friendship.Status.ACCEPTED:
        return friendship, "friends"

    if friendship.requester_id == current_user.pk:
        return friendship, "sent"

    return friendship, "received"


def signup(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if request.method == "POST":
        form = SignUpForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect("home")
    else:
        form = SignUpForm()

    return render(
        request,
        "registration/signup.html",
        {
            "form": form,
            "next": next_url,
        },
    )


@login_required
def hub(request):
    return render(request, "hub.html")


@login_required
def lobby(request):
    if request.method == "POST":
        game = Game.objects.create(
            created_by=request.user,
        )

        GameEngine(game).add_player(request.user)

        return redirect(
            "game_detail",
            game_id=game.id,
        )

    open_games = Game.objects.filter(
        status=Game.Status.EN_ATTENTE,
    ).select_related("created_by")

    my_games = Game.objects.filter(
        players__user=request.user,
    ).exclude(
        status=Game.Status.EN_ATTENTE,
    )

    return render(
        request,
        "game/lobby.html",
        {
            "open_games": open_games,
            "my_games": my_games,
            "lobby_state": get_lobby_state(request.user),
        },
    )


@login_required
@require_POST
@transaction.atomic
def join_game(request, game_id):
    game = get_object_or_404(
        Game.objects.select_for_update(),
        pk=game_id,
    )

    try:
        GameEngine(game).add_player(request.user)
    except GameEngineError as exc:
        messages.error(
            request,
            str(exc),
        )
        return redirect("lobby")

    invalidate_game_state_cache(game)

    return redirect(
        "game_detail",
        game_id=game.id,
    )


@login_required
@require_POST
@transaction.atomic
def start_game_view(request, game_id):
    game = get_object_or_404(
        Game.objects.select_for_update(),
        pk=game_id,
    )

    if game.created_by_id != request.user.id:
        return HttpResponseForbidden("Seul le créateur de la partie peut la démarrer.")

    try:
        GameEngine(game).start_game()
    except GameEngineError as exc:
        messages.error(
            request,
            str(exc),
        )

    invalidate_game_state_cache(game)

    return redirect(
        "game_detail",
        game_id=game.id,
    )


@login_required
@require_POST
@transaction.atomic
def add_bot_view(request, game_id):
    game = get_object_or_404(
        Game.objects.select_for_update(),
        pk=game_id,
    )

    if game.created_by_id != request.user.id:
        return HttpResponseForbidden("Seul le créateur peut ajouter une IA.")

    try:
        GameEngine(game).add_bot()
    except GameEngineError as exc:
        messages.error(
            request,
            str(exc),
        )

    invalidate_game_state_cache(game)

    return redirect(
        "game_detail",
        game_id=game.id,
    )


@login_required
@require_POST
@transaction.atomic
def remove_bot_view(request, game_id, player_id):
    game = get_object_or_404(
        Game.objects.select_for_update(),
        pk=game_id,
    )

    if game.created_by_id != request.user.id:
        return HttpResponseForbidden("Seul le créateur peut retirer une IA.")

    try:
        GameEngine(game).remove_bot(player_id)
    except GameEngineError as exc:
        messages.error(
            request,
            str(exc),
        )

    invalidate_game_state_cache(game)

    return redirect(
        "game_detail",
        game_id=game.id,
    )


@login_required
def game_detail(request, game_id):
    close_stale_games()

    game = get_object_or_404(
        Game,
        pk=game_id,
    )

    game_player = game.players.filter(
        user=request.user,
    ).first()

    if game_player is None:
        player_count = game.players.count()

        can_join = game.status == Game.Status.EN_ATTENTE and player_count < game.max_players

        return render(
            request,
            "join_invitation.html",
            {
                "mode_name": "Poké-Uno",
                "mode_kicker": ("Défausse · pouvoirs · types Pokémon"),
                "host_name": game.created_by.get_username(),
                "player_count": player_count,
                "max_players": game.max_players,
                "can_join": can_join,
                "join_url": reverse(
                    "join_game",
                    kwargs={
                        "game_id": game.id,
                    },
                ),
                "lobby_url": reverse("lobby"),
            },
            status=200 if can_join else 403,
        )

    game_state = GameEngine(game).get_game_state(
        for_player=game_player,
    )

    players_state = game_state["players"]

    my_index = next(index for index, player in enumerate(players_state) if "hand" in player)

    my_player = players_state[my_index]

    seat_order = players_state[my_index + 1 :] + players_state[:my_index]

    opponents = [
        {
            **player,
            "card_back_slots": range(
                min(
                    player["hand_count"],
                    OPPONENT_CARD_BACK_LIMIT,
                )
            ),
            "hidden_card_count": max(
                0,
                (player["hand_count"] - OPPONENT_CARD_BACK_LIMIT),
            ),
        }
        for player in seat_order
        if "hand" not in player
    ]

    if game.status == Game.Status.EN_COURS:
        engine = GameEngine(game)

        hand_cards = GameCard.objects.select_related(
            "pokemon_card",
        ).filter(
            game=game,
            location=GameCard.Location.MAIN,
            owner=game_player,
        )

        playable_by_id = {
            game_card.id: engine.is_move_valid(
                game_player,
                game_card,
            )[0]
            for game_card in hand_cards
        }

        for card in my_player["hand"]:
            card["is_playable"] = playable_by_id[card["id"]]

    return render(
        request,
        "game/detail.html",
        {
            "game": game,
            "is_creator": (game.created_by_id == request.user.id),
            "players": game.players.select_related("user").all(),
            "game_state": game_state,
            "my_player": my_player,
            "opponents": opponents,
            "game_types": (
                game_state.get(
                    "game_types",
                    [],
                )
                if game_state
                else []
            ),
            "all_types": [pokemon_type.as_dict() for pokemon_type in POKEMON_TYPES],
        },
    )


@login_required
def my_profile(request):
    """Affiche le profil de l'utilisateur connecté."""

    profile, _ = Profile.objects.get_or_create(
        user=request.user,
    )

    return render(
        request,
        "game/profile/detail.html",
        {
            "profile_user": request.user,
            "profile": profile,
            "is_owner": True,
            "friendship": None,
            "friendship_status": "self",
        },
    )


@login_required
def public_profile(request, username):
    """Affiche le profil public d'un joueur."""

    profile_user = get_object_or_404(
        User,
        username=username,
    )

    profile, _ = Profile.objects.get_or_create(
        user=profile_user,
    )

    friendship, friendship_status = _get_relationship(
        request.user,
        profile_user,
    )

    return render(
        request,
        "game/profile/detail.html",
        {
            "profile_user": profile_user,
            "profile": profile,
            "is_owner": (profile_user.pk == request.user.pk),
            "friendship": friendship,
            "friendship_status": friendship_status,
        },
    )


@login_required
@transaction.atomic
def edit_profile(request):
    """Permet de modifier le compte et le profil connecté."""

    profile, _ = Profile.objects.get_or_create(
        user=request.user,
    )

    if request.method == "POST":
        account_form = AccountForm(
            request.POST,
            instance=request.user,
        )

        profile_form = ProfileForm(
            request.POST,
            request.FILES,
            instance=profile,
        )

        if account_form.is_valid() and profile_form.is_valid():
            account_form.save()
            profile_form.save()

            messages.success(
                request,
                "Ton profil a bien été mis à jour.",
            )

            return redirect("my_profile")
    else:
        account_form = AccountForm(
            instance=request.user,
        )

        profile_form = ProfileForm(
            instance=profile,
        )

    return render(
        request,
        "game/profile/edit.html",
        {
            "account_form": account_form,
            "profile_form": profile_form,
            "profile": profile,
        },
    )


@login_required
def friends(request):
    """Affiche les amis et les demandes de l'utilisateur."""

    accepted_friendships = (
        Friendship.objects.filter(
            (Q(requester=request.user) | Q(addressee=request.user)),
            status=Friendship.Status.ACCEPTED,
        )
        .select_related(
            "requester",
            "addressee",
        )
        .order_by("-updated_at")
    )

    friend_entries = []

    for friendship in accepted_friendships:
        friend_user = friendship.get_other_user(
            request.user,
        )

        profile, _ = Profile.objects.get_or_create(
            user=friend_user,
        )

        friend_entries.append(
            {
                "user": friend_user,
                "profile": profile,
                "friendship": friendship,
            }
        )

    received_requests = list(
        Friendship.objects.filter(
            addressee=request.user,
            status=Friendship.Status.PENDING,
        )
        .select_related(
            "requester",
            "requester__profile",
        )
        .order_by("-created_at")
    )

    sent_requests = list(
        Friendship.objects.filter(
            requester=request.user,
            status=Friendship.Status.PENDING,
        )
        .select_related(
            "addressee",
            "addressee__profile",
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "game/profile/friends.html",
        {
            "friend_entries": friend_entries,
            "received_requests": received_requests,
            "sent_requests": sent_requests,
        },
    )


@login_required
def player_search(request):
    """Recherche des joueurs par pseudo, prénom ou nom."""

    query = request.GET.get(
        "q",
        "",
    ).strip()

    search_results = []

    if query:
        players = (
            User.objects.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
            )
            .exclude(pk=request.user.pk)
            .order_by("username")[:30]
        )

        for player in players:
            profile, _ = Profile.objects.get_or_create(
                user=player,
            )

            friendship, status = _get_relationship(
                request.user,
                player,
            )

            search_results.append(
                {
                    "user": player,
                    "profile": profile,
                    "friendship": friendship,
                    "status": status,
                }
            )

    return render(
        request,
        "game/profile/search.html",
        {
            "query": query,
            "search_results": search_results,
        },
    )


@login_required
@require_POST
@transaction.atomic
def send_friend_request(request, username):
    """Envoie ou renouvelle une demande d'ami."""

    target_user = get_object_or_404(
        User,
        username=username,
    )

    if target_user.pk == request.user.pk:
        messages.error(
            request,
            "Tu ne peux pas t’ajouter toi-même.",
        )

        return redirect("my_profile")

    pair_key = _friendship_pair_key(
        request.user,
        target_user,
    )

    friendship = Friendship.objects.select_for_update().filter(pair_key=pair_key).first()

    if friendship is None:
        Friendship.objects.create(
            requester=request.user,
            addressee=target_user,
        )

        messages.success(
            request,
            ("Demande d’ami envoyée à " f"{target_user.username}."),
        )

    elif friendship.status == Friendship.Status.ACCEPTED:
        messages.info(
            request,
            ("Tu es déjà ami avec " f"{target_user.username}."),
        )

    elif friendship.status == Friendship.Status.PENDING:
        if friendship.requester_id == request.user.pk:
            messages.info(
                request,
                "Cette demande d’ami est déjà en attente.",
            )
        else:
            friendship.status = Friendship.Status.ACCEPTED

            friendship.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            messages.success(
                request,
                ("Tu es maintenant ami avec " f"{target_user.username}."),
            )

    else:
        friendship.requester = request.user
        friendship.addressee = target_user
        friendship.status = Friendship.Status.PENDING
        friendship.save()

        messages.success(
            request,
            ("Nouvelle demande envoyée à " f"{target_user.username}."),
        )

    return redirect(
        "public_profile",
        username=target_user.username,
    )


@login_required
@require_POST
@transaction.atomic
def accept_friend_request(request, friendship_id):
    """Accepte une demande reçue."""

    friendship = get_object_or_404(
        Friendship.objects.select_for_update(),
        pk=friendship_id,
        addressee=request.user,
        status=Friendship.Status.PENDING,
    )

    friendship.status = Friendship.Status.ACCEPTED

    friendship.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    messages.success(
        request,
        ("Tu es maintenant ami avec " f"{friendship.requester.username}."),
    )

    return redirect("friends")


@login_required
@require_POST
@transaction.atomic
def reject_friend_request(request, friendship_id):
    """Refuse une demande reçue."""

    friendship = get_object_or_404(
        Friendship.objects.select_for_update(),
        pk=friendship_id,
        addressee=request.user,
        status=Friendship.Status.PENDING,
    )

    friendship.status = Friendship.Status.REJECTED

    friendship.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    messages.info(
        request,
        "La demande d’ami a été refusée.",
    )

    return redirect("friends")


@login_required
@require_POST
@transaction.atomic
def cancel_friend_request(request, friendship_id):
    """Annule une demande envoyée."""

    friendship = get_object_or_404(
        Friendship.objects.select_for_update(),
        pk=friendship_id,
        requester=request.user,
        status=Friendship.Status.PENDING,
    )

    friendship.delete()

    messages.info(
        request,
        "La demande d’ami a été annulée.",
    )

    return redirect("friends")


@login_required
@require_POST
@transaction.atomic
def remove_friend(request, friendship_id):
    """Supprime une relation d'amitié acceptée."""

    friendship = get_object_or_404(
        Friendship.objects.select_for_update().filter(
            (Q(requester=request.user) | Q(addressee=request.user)),
            status=Friendship.Status.ACCEPTED,
        ),
        pk=friendship_id,
    )

    other_user = friendship.get_other_user(
        request.user,
    )

    friendship.delete()

    messages.info(
        request,
        (f"{other_user.username} a été retiré " "de ta liste d’amis."),
    )

    return redirect("friends")
