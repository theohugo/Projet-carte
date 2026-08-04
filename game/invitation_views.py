from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from game.api import invalidate_game_state_cache
from game.game_engine import GameEngine, GameEngineError
from game.models import (
    Friendship,
    Game,
    GameInvitation,
    Profile,
)
from guesswho.models import GuessWhoGame
from guesswho.services import (
    GuessWhoError,
)
from guesswho.services import (
    join_game as join_guesswho_game,
)
from pictionary.models import PictionaryGame
from pictionary.services import (
    PictionaryError,
)
from pictionary.services import (
    join_game as join_pictionary_game,
)
from silhouette.models import SilhouetteGame
from silhouette.services import (
    SilhouetteError,
)
from silhouette.services import (
    join_game as join_silhouette_game,
)

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
}


MODE_BY_SLUG = {config["slug"]: mode for mode, config in MODE_CONFIG.items()}


INVITATION_SELECT_RELATED = (
    "game",
    "guesswho_game",
    "silhouette_game",
    "pictionary_game",
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
    invitation.mode_label_value = invitation.get_mode_display()

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


@login_required
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


@login_required
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
        return HttpResponseForbidden("Seul le créateur du salon peut inviter des amis.")

    if not _room_is_waiting(
        config,
        room,
    ):
        messages.error(
            request,
            ("Cette partie n’accepte plus " "de nouvelles invitations."),
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
            "mode_label": dict(GameInvitation.Mode.choices)[mode_value],
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


@login_required
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
        return HttpResponseForbidden("Seul le créateur du salon peut inviter des amis.")

    if not _room_is_waiting(
        config,
        room,
    ):
        messages.error(
            request,
            ("Cette partie a déjà commencé " "ou est terminée."),
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
            "Le salon est déjà complet.",
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
            "Tu ne peux pas t’inviter toi-même.",
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
        return HttpResponseForbidden("Tu ne peux inviter que les joueurs " "présents dans ta liste d’amis.")

    if _room_has_player(
        room,
        recipient,
    ):
        messages.info(
            request,
            (f"{recipient.username} est déjà " "dans le salon."),
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
            ("Une invitation est déjà en attente " f"pour {recipient.username}."),
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

    mode_label = dict(GameInvitation.Mode.choices)[mode_value]

    messages.success(
        request,
        (f"Invitation {mode_label} envoyée " f"à {recipient.username}."),
    )

    return redirect(
        "invite_friends_to_game",
        mode=config["slug"],
        room_id=room.pk,
    )


@login_required
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
            "Cette invitation n’est plus disponible.",
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
            ("Cette invitation a expiré : " "la partie a déjà commencé."),
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
            "Tu participes déjà à cette partie.",
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
            ("Cette invitation a expiré : " "le salon est complet."),
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
        (
            f"Invitation {invitation.get_mode_display()} "
            f"acceptée. Tu as rejoint le salon de "
            f"{invitation.sender.username}."
        ),
    )

    return redirect(
        _room_detail_url(
            config,
            room,
        )
    )


@login_required
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
        "L’invitation a été refusée.",
    )

    return redirect("game_invitations")


@login_required
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
        "L’invitation a été annulée.",
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
