from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from game.api import invalidate_game_state_cache
from game.game_engine import GameEngine, GameEngineError
from game.guests import member_feature, members_only
from game.models import (
    Friendship,
    Game,
    GameInvitation,
    Profile,
)
from game.pokemon_names import bilingual_text
from guesswho.models import GuessWhoGame
from guesswho.services import (
    GuessWhoError,
)
from guesswho.services import (
    join_game as join_guesswho_game,
)
from islands.models import IslandGame
from islands.services import IslandError
from islands.services import join_game as join_islands_game
from metamorph.models import MetamorphGame
from metamorph.services import MetamorphError
from metamorph.services import join_game as join_metamorph_game
from pictionary.models import PictionaryGame
from pictionary.services import (
    PictionaryError,
)
from pictionary.services import (
    join_game as join_pictionary_game,
)
from rocket.models import RocketGame
from rocket.services import RocketError
from rocket.services import join_game as join_rocket_game
from silhouette.models import SilhouetteGame
from silhouette.services import (
    SilhouetteError,
)
from silhouette.services import (
    join_game as join_silhouette_game,
)
from starterrace.models import Game as StarterRaceGame
from starterrace.services import StarterRaceError
from starterrace.services import join_game as join_starterrace_game

User = get_user_model()


def _join_poke_uno(room, user):
    """Ajoute un joueur à une partie Poké-Uno."""

    GameEngine(room).add_player(user)
    invalidate_game_state_cache(room)


def _join_guesswho(room, user):
    """Ajoute un joueur à une partie Qui est-ce ?."""

    join_guesswho_game(room.pk, user)


def _join_silhouette(room, user):
    """Ajoute un joueur à une partie Silhouette."""

    join_silhouette_game(room.pk, user)


def _join_pictionary(room, user):
    """Ajoute un joueur à une partie Pictionary."""

    join_pictionary_game(room.pk, user)


def _join_metamorph(room, user):
    join_metamorph_game(room.pk, user)


def _join_rocket(room, user):
    join_rocket_game(room.pk, user)


def _join_islands(room, user):
    join_islands_game(room.pk, user)


def _join_starterrace(room, user):
    join_starterrace_game(room.pk, user)


MODE_CONFIG = {
    GameInvitation.Mode.POKE_UNO: {
        "slug": "poke-uno",
        "model": Game,
        "room_field": "game",
        "waiting_status": Game.Status.EN_ATTENTE,
        "detail_url": "game_detail",
        "lobby_url": "lobby",
        "joiner": _join_poke_uno,
        "errors": (GameEngineError,),
    },
    GameInvitation.Mode.GUESSWHO: {
        "slug": "qui-est-ce",
        "model": GuessWhoGame,
        "room_field": "guesswho_game",
        "waiting_status": GuessWhoGame.Status.EN_ATTENTE,
        "detail_url": "guesswho:game_detail",
        "lobby_url": "guesswho:lobby",
        "joiner": _join_guesswho,
        "errors": (GuessWhoError,),
    },
    GameInvitation.Mode.SILHOUETTE: {
        "slug": "silhouette",
        "model": SilhouetteGame,
        "room_field": "silhouette_game",
        "waiting_status": SilhouetteGame.Status.EN_ATTENTE,
        "detail_url": "silhouette:game_detail",
        "lobby_url": "silhouette:lobby",
        "joiner": _join_silhouette,
        "errors": (SilhouetteError,),
    },
    GameInvitation.Mode.PICTIONARY: {
        "slug": "pictionary",
        "model": PictionaryGame,
        "room_field": "pictionary_game",
        "waiting_status": PictionaryGame.Status.EN_ATTENTE,
        "detail_url": "pictionary:game_detail",
        "lobby_url": "pictionary:lobby",
        "joiner": _join_pictionary,
        "errors": (PictionaryError,),
    },
    GameInvitation.Mode.METAMORPH: {
        "slug": "metamorph-mystere",
        "model": MetamorphGame,
        "room_field": "metamorph_game",
        "waiting_status": MetamorphGame.Status.EN_ATTENTE,
        "detail_url": "metamorph:game_detail",
        "lobby_url": "metamorph:lobby",
        "joiner": _join_metamorph,
        "errors": (MetamorphError,),
    },
    GameInvitation.Mode.ROCKET: {
        "slug": "infiltration-rocket",
        "model": RocketGame,
        "room_field": "rocket_game",
        "waiting_status": RocketGame.Status.EN_ATTENTE,
        "detail_url": "rocket:game_detail",
        "lobby_url": "rocket:lobby",
        "joiner": _join_rocket,
        "errors": (RocketError,),
    },
    GameInvitation.Mode.ISLANDS: {
        "slug": "bataille-des-iles",
        "model": IslandGame,
        "room_field": "islands_game",
        "waiting_status": IslandGame.Status.EN_ATTENTE,
        "detail_url": "islands:game_detail",
        "lobby_url": "islands:lobby",
        "joiner": _join_islands,
        "errors": (IslandError,),
    },
    GameInvitation.Mode.STARTER_RACE: {
        "slug": "course-des-starters",
        "model": StarterRaceGame,
        "room_field": "starterrace_game",
        "waiting_status": StarterRaceGame.Status.EN_ATTENTE,
        "detail_url": "starterrace:game_detail",
        "lobby_url": "starterrace:lobby",
        "joiner": _join_starterrace,
        "errors": (StarterRaceError,),
    },
}


MODE_BY_SLUG = {config["slug"]: mode for mode, config in MODE_CONFIG.items()}

MODE_LABELS_EN = {
    GameInvitation.Mode.POKE_UNO: "Poké-Uno",
    GameInvitation.Mode.GUESSWHO: "Guess Who?",
    GameInvitation.Mode.SILHOUETTE: "Who’s That Pokémon?",
    GameInvitation.Mode.PICTIONARY: "Pictionary",
    GameInvitation.Mode.METAMORPH: "Ditto Mystery",
    GameInvitation.Mode.ROCKET: "Team Rocket Infiltration",
    GameInvitation.Mode.ISLANDS: "Island Battle",
    GameInvitation.Mode.STARTER_RACE: "Starter Race",
}


def _mode_label(mode):
    return bilingual_text(dict(GameInvitation.Mode.choices)[mode], MODE_LABELS_EN[mode])


INVITATION_SELECT_RELATED = (
    "game",
    "guesswho_game",
    "silhouette_game",
    "pictionary_game",
    "metamorph_game",
    "rocket_game",
    "islands_game",
    "starterrace_game",
    "sender",
    "sender__profile",
    "recipient",
    "recipient__profile",
)


def _friendship_pair_key(first_user, second_user):
    """Construit la clé unique commune à deux utilisateurs."""

    first_id, second_id = sorted(
        (
            first_user.pk,
            second_user.pk,
        )
    )

    return f"{first_id}:{second_id}"


def _are_friends(first_user, second_user):
    """Vérifie que deux utilisateurs sont amis."""

    if first_user.pk == second_user.pk:
        return False

    return Friendship.objects.filter(
        pair_key=_friendship_pair_key(
            first_user,
            second_user,
        ),
        status=Friendship.Status.ACCEPTED,
    ).exists()


def _get_mode_and_config(mode_slug):
    """Résout le mode reçu depuis l’URL."""

    mode = MODE_BY_SLUG.get(mode_slug)

    if mode is None:
        raise Http404("Ce mode de jeu n’existe pas.")

    return mode, MODE_CONFIG[mode]


def _get_config_from_invitation(invitation):
    """Retourne la configuration du mode d’une invitation."""

    config = MODE_CONFIG.get(invitation.mode)

    if config is None:
        raise Http404("Le mode de cette invitation n’existe plus.")

    return config


def _get_room(config, room_id, *, lock=False):
    """Charge un salon depuis le modèle associé au mode."""

    queryset = config["model"].objects.all()

    if lock:
        queryset = queryset.select_for_update()

    return get_object_or_404(
        queryset,
        pk=room_id,
    )


def _room_detail_url(config, room):
    """Construit l’adresse de la page du salon."""

    return reverse(
        config["detail_url"],
        kwargs={
            "game_id": room.pk,
        },
    )


def _room_is_waiting(config, room):
    """Vérifie que le salon attend encore des joueurs."""

    return room.status == config["waiting_status"]


def _room_max_players(room):
    """Retourne le nombre maximal de joueurs ou None si illimité."""

    max_players = getattr(
        room,
        "max_players",
        None,
    )

    if callable(max_players):
        max_players = max_players()

    return max_players


def _room_is_full(room):
    """Vérifie si le salon a atteint sa limite."""

    max_players = _room_max_players(room)

    if max_players is None:
        return False

    return room.players.count() >= max_players


def _room_has_player(room, user):
    """Vérifie qu’un utilisateur participe déjà au salon."""

    return room.players.filter(
        user=user,
    ).exists()


def _invitation_room_filter(config, room):
    """Construit le filtre correspondant au champ du salon."""

    return {
        config["room_field"]: room,
    }


def _decorate_invitation(invitation):
    """Ajoute les informations nécessaires au template."""

    config = _get_config_from_invitation(
        invitation,
    )

    room = invitation.room

    invitation.mode_slug_value = config["slug"]
    invitation.mode_label_value = _mode_label(invitation.mode)

    if room is None:
        invitation.detail_url = ""
        invitation.player_count = 0
        invitation.max_players_display = 0

        return invitation

    invitation.detail_url = _room_detail_url(
        config,
        room,
    )

    invitation.player_count = room.players.count()

    max_players = _room_max_players(room)

    invitation.max_players_display = max_players if max_players is not None else "∞"

    return invitation


def _expire_invitation(invitation):
    """Marque une invitation comme expirée."""

    invitation.status = GameInvitation.Status.EXPIRED
    invitation.responded_at = timezone.now()

    invitation.save(
        update_fields=[
            "status",
            "responded_at",
            "updated_at",
        ]
    )


def _active_pending_invitations(queryset):
    """Garde uniquement les invitations de salons encore ouverts."""

    active_invitations = []

    for invitation in queryset:
        config = MODE_CONFIG.get(
            invitation.mode,
        )

        room = invitation.room

        if (
            config is None
            or room is None
            or not _room_is_waiting(
                config,
                room,
            )
        ):
            _expire_invitation(invitation)
            continue

        active_invitations.append(_decorate_invitation(invitation))

    return active_invitations


@members_only
@member_feature(
    "Tes invitations",
    "Invite tes amis en un clic et retrouve toutes les parties où l'on t'attend.",
    label_en="Your invitations",
    promise_en="Invite friends in one click and find every game waiting for you.",
)
def game_invitations(request):
    """Affiche les invitations reçues et envoyées."""

    received_queryset = (
        GameInvitation.objects.filter(
            recipient=request.user,
            status=GameInvitation.Status.PENDING,
        )
        .select_related(*INVITATION_SELECT_RELATED)
        .order_by("-created_at")
    )

    sent_queryset = (
        GameInvitation.objects.filter(
            sender=request.user,
            status=GameInvitation.Status.PENDING,
        )
        .select_related(*INVITATION_SELECT_RELATED)
        .order_by("-created_at")
    )

    received_invitations = _active_pending_invitations(received_queryset)

    sent_invitations = _active_pending_invitations(sent_queryset)

    return render(
        request,
        "game/invitations/list.html",
        {
            "received_invitations": (received_invitations),
            "sent_invitations": sent_invitations,
        },
    )


@members_only
def invite_friends_to_game(
    request,
    mode,
    room_id,
):
    """Affiche les amis pouvant être invités dans un salon."""

    mode_value, config = _get_mode_and_config(mode)

    room = _get_room(
        config,
        room_id,
    )

    if room.created_by_id != request.user.id:
        return HttpResponseForbidden(
            bilingual_text(
                "Seul le créateur du salon peut inviter des amis.",
                "Only the room host can invite friends.",
            )
        )

    if not _room_is_waiting(
        config,
        room,
    ):
        messages.error(
            request,
            bilingual_text(
                "Cette partie n’accepte plus de nouvelles invitations.",
                "This game no longer accepts new invitations.",
            ),
        )

        return redirect(
            _room_detail_url(
                config,
                room,
            )
        )

    accepted_friendships = (
        Friendship.objects.filter(
            Q(requester=request.user) | Q(addressee=request.user),
            status=Friendship.Status.ACCEPTED,
        )
        .select_related(
            "requester",
            "addressee",
        )
        .order_by("-updated_at")
    )

    participant_ids = set(
        room.players.exclude(
            user_id=None,
        ).values_list(
            "user_id",
            flat=True,
        )
    )

    room_filter = _invitation_room_filter(
        config,
        room,
    )

    pending_invitations = {
        invitation.recipient_id: invitation
        for invitation in (
            GameInvitation.objects.filter(
                mode=mode_value,
                sender=request.user,
                status=GameInvitation.Status.PENDING,
                **room_filter,
            ).select_related("recipient")
        )
    }

    friend_entries = []

    for friendship in accepted_friendships:
        friend_user = friendship.get_other_user(
            request.user,
        )

        profile, _ = Profile.objects.get_or_create(
            user=friend_user,
        )

        if friend_user.pk in participant_ids:
            invitation_status = "joined"
            invitation = None

        elif friend_user.pk in pending_invitations:
            invitation_status = "pending"

            invitation = pending_invitations[friend_user.pk]

        else:
            invitation_status = "available"
            invitation = None

        friend_entries.append(
            {
                "user": friend_user,
                "profile": profile,
                "status": invitation_status,
                "invitation": invitation,
            }
        )

    max_players = _room_max_players(room)

    return render(
        request,
        "game/invitations/select_friend.html",
        {
            "room": room,
            "mode_slug": config["slug"],
            "mode_label": _mode_label(mode_value),
            "room_detail_url": _room_detail_url(
                config,
                room,
            ),
            "friend_entries": friend_entries,
            "game_is_full": _room_is_full(room),
            "player_count": room.players.count(),
            "max_players": (max_players if max_players is not None else "∞"),
        },
    )


@members_only
@require_POST
@transaction.atomic
def send_game_invitation(
    request,
    mode,
    room_id,
    username,
):
    """Envoie une invitation pour le jeu choisi."""

    mode_value, config = _get_mode_and_config(mode)

    room = _get_room(
        config,
        room_id,
        lock=True,
    )

    if room.created_by_id != request.user.id:
        return HttpResponseForbidden(
            bilingual_text(
                "Seul le créateur du salon peut inviter des amis.",
                "Only the room host can invite friends.",
            )
        )

    if not _room_is_waiting(
        config,
        room,
    ):
        messages.error(
            request,
            bilingual_text(
                "Cette partie a déjà commencé ou est terminée.",
                "This game has already started or ended.",
            ),
        )

        return redirect(
            _room_detail_url(
                config,
                room,
            )
        )

    if _room_is_full(room):
        messages.error(
            request,
            bilingual_text("Le salon est déjà complet.", "The room is already full."),
        )

        return redirect(
            "invite_friends_to_game",
            mode=config["slug"],
            room_id=room.pk,
        )

    recipient = get_object_or_404(
        User,
        username=username,
    )

    if recipient.pk == request.user.pk:
        messages.error(
            request,
            bilingual_text("Tu ne peux pas t’inviter toi-même.", "You cannot invite yourself."),
        )

        return redirect(
            "invite_friends_to_game",
            mode=config["slug"],
            room_id=room.pk,
        )

    if not _are_friends(
        request.user,
        recipient,
    ):
        return HttpResponseForbidden(
            bilingual_text(
                "Tu ne peux inviter que les joueurs présents dans ta liste d’amis.",
                "You can only invite players on your friends list.",
            )
        )

    if _room_has_player(
        room,
        recipient,
    ):
        messages.info(
            request,
            bilingual_text(
                f"{recipient.username} est déjà dans le salon.",
                f"{recipient.username} is already in the room.",
            ),
        )

        return redirect(
            "invite_friends_to_game",
            mode=config["slug"],
            room_id=room.pk,
        )

    room_filter = _invitation_room_filter(
        config,
        room,
    )

    existing_invitation = (
        GameInvitation.objects.filter(
            mode=mode_value,
            recipient=recipient,
            status=GameInvitation.Status.PENDING,
            **room_filter,
        )
        .select_related("recipient")
        .first()
    )

    if existing_invitation:
        messages.info(
            request,
            bilingual_text(
                f"Une invitation est déjà en attente pour {recipient.username}.",
                f"An invitation for {recipient.username} is already pending.",
            ),
        )

        return redirect(
            "invite_friends_to_game",
            mode=config["slug"],
            room_id=room.pk,
        )

    invitation_values = {
        "mode": mode_value,
        "sender": request.user,
        "recipient": recipient,
        config["room_field"]: room,
    }

    GameInvitation.objects.create(**invitation_values)

    mode_label = _mode_label(mode_value)

    messages.success(
        request,
        bilingual_text(
            f"Invitation {mode_label} envoyée à {recipient.username}.",
            f"{mode_label} invitation sent to {recipient.username}.",
        ),
    )

    return redirect(
        "invite_friends_to_game",
        mode=config["slug"],
        room_id=room.pk,
    )


@members_only
@require_POST
@transaction.atomic
def accept_game_invitation(
    request,
    invitation_id,
):
    """Accepte une invitation et rejoint le bon salon."""

    # On verrouille uniquement GameInvitation.
    #
    # Il ne faut pas ajouter select_related() à cette requête :
    # les relations vers les différents salons sont facultatives.
    # PostgreSQL refuse FOR UPDATE sur les côtés nullables
    # produits par les LEFT OUTER JOIN.
    invitation = get_object_or_404(
        GameInvitation.objects.select_for_update(),
        pk=invitation_id,
        recipient=request.user,
        status=GameInvitation.Status.PENDING,
    )

    config = _get_config_from_invitation(
        invitation,
    )

    original_room = invitation.room

    if original_room is None:
        _expire_invitation(invitation)

        messages.error(
            request,
            bilingual_text(
                "Cette invitation n’est plus disponible.",
                "This invitation is no longer available.",
            ),
        )

        return redirect("game_invitations")

    # Le salon est verrouillé séparément dans une deuxième requête.
    room = _get_room(
        config,
        original_room.pk,
        lock=True,
    )

    if not _room_is_waiting(
        config,
        room,
    ):
        _expire_invitation(invitation)

        messages.error(
            request,
            bilingual_text(
                "Cette invitation a expiré : la partie a déjà commencé.",
                "This invitation expired because the game already started.",
            ),
        )

        return redirect("game_invitations")

    if _room_has_player(
        room,
        request.user,
    ):
        invitation.status = GameInvitation.Status.ACCEPTED
        invitation.responded_at = timezone.now()

        invitation.save(
            update_fields=[
                "status",
                "responded_at",
                "updated_at",
            ]
        )

        messages.info(
            request,
            bilingual_text("Tu participes déjà à cette partie.", "You are already in this game."),
        )

        return redirect(
            _room_detail_url(
                config,
                room,
            )
        )

    if _room_is_full(room):
        _expire_invitation(invitation)

        messages.error(
            request,
            bilingual_text(
                "Cette invitation a expiré : le salon est complet.",
                "This invitation expired because the room is full.",
            ),
        )

        return redirect("game_invitations")

    try:
        config["joiner"](
            room,
            request.user,
        )

    except config["errors"] as exc:
        messages.error(
            request,
            str(exc),
        )

        return redirect("game_invitations")

    invitation.status = GameInvitation.Status.ACCEPTED
    invitation.responded_at = timezone.now()

    invitation.save(
        update_fields=[
            "status",
            "responded_at",
            "updated_at",
        ]
    )

    messages.success(
        request,
        bilingual_text(
            f"Invitation {_mode_label(invitation.mode)} acceptée. "
            f"Tu as rejoint le salon de {invitation.sender.username}.",
            f"{_mode_label(invitation.mode)} invitation accepted. "
            f"You joined {invitation.sender.username}'s room.",
        ),
    )

    return redirect(
        _room_detail_url(
            config,
            room,
        )
    )


@members_only
@require_POST
@transaction.atomic
def decline_game_invitation(
    request,
    invitation_id,
):
    """Refuse une invitation reçue."""

    invitation = get_object_or_404(
        GameInvitation.objects.select_for_update(),
        pk=invitation_id,
        recipient=request.user,
        status=GameInvitation.Status.PENDING,
    )

    invitation.status = GameInvitation.Status.DECLINED
    invitation.responded_at = timezone.now()

    invitation.save(
        update_fields=[
            "status",
            "responded_at",
            "updated_at",
        ]
    )

    messages.info(
        request,
        bilingual_text("L’invitation a été refusée.", "The invitation was declined."),
    )

    return redirect("game_invitations")


@members_only
@require_POST
@transaction.atomic
def cancel_game_invitation(
    request,
    invitation_id,
):
    """Annule une invitation envoyée."""

    # Comme pour l’acceptation, on verrouille seulement
    # la ligne GameInvitation, sans select_related().
    invitation = get_object_or_404(
        GameInvitation.objects.select_for_update(),
        pk=invitation_id,
        sender=request.user,
        status=GameInvitation.Status.PENDING,
    )

    config = _get_config_from_invitation(
        invitation,
    )

    room = invitation.room

    invitation.status = GameInvitation.Status.CANCELLED
    invitation.responded_at = timezone.now()

    invitation.save(
        update_fields=[
            "status",
            "responded_at",
            "updated_at",
        ]
    )

    messages.info(
        request,
        bilingual_text("L’invitation a été annulée.", "The invitation was cancelled."),
    )

    if room is not None and _room_is_waiting(
        config,
        room,
    ):
        return redirect(
            "invite_friends_to_game",
            mode=config["slug"],
            room_id=room.pk,
        )

    return redirect("game_invitations")
