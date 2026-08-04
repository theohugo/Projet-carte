"""Mode invité : jouer sans créer de compte.

Un invité est un vrai ``User``, marqué ``Profile.is_guest``, créé à la volée et
connecté par session. Ce choix évite de rendre chaque joueur nullable dans les
quatre jeux : le moteur, les scores et les parties fonctionnent exactement comme
pour un membre. En échange, l'invité n'a pas de mot de passe utilisable, ne
garde rien au-delà de sa session, et les pages personnelles (collection, quêtes,
amis, invitations, profil) lui restent fermées — c'est précisément ce qui donne
envie de créer un compte.
"""

import secrets
from functools import wraps

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

GUEST_USERNAME_PREFIX = "Invité-"
# Assez large pour ne pas tomber deux fois sur le même nom, assez court pour
# rester lisible dans un salon.
GUEST_SUFFIX_DIGITS = 4
GUEST_MAX_ATTEMPTS = 12
# Au-delà, un invité qui n'est jamais revenu n'a plus rien à sauvegarder.
GUEST_RETENTION_DAYS = 7


def is_guest(user) -> bool:
    """Vrai si l'utilisateur connecté joue en invité."""

    if not getattr(user, "is_authenticated", False):
        return False
    profile = getattr(user, "profile", None)
    return bool(profile and profile.is_guest)


def is_member(user) -> bool:
    """Vrai pour un compte complet : ni anonyme, ni invité."""

    return getattr(user, "is_authenticated", False) and not is_guest(user)


@transaction.atomic
def create_guest_user() -> User:
    """Crée un compte invité au nom lisible et sans mot de passe utilisable."""

    for _ in range(GUEST_MAX_ATTEMPTS):
        suffix = secrets.randbelow(10**GUEST_SUFFIX_DIGITS)
        username = f"{GUEST_USERNAME_PREFIX}{suffix:0{GUEST_SUFFIX_DIGITS}d}"
        if User.objects.filter(username=username).exists():
            continue

        user = User.objects.create_user(username=username)
        user.set_unusable_password()
        user.save(update_fields=["password"])
        # Le profil est créé par un signal : on ne fait que le marquer.
        profile = user.profile
        profile.is_guest = True
        profile.save(update_fields=["is_guest"])
        return user

    raise RuntimeError("Impossible de trouver un nom d'invité disponible.")


def start_guest_session(request) -> User:
    """Crée un invité et l'authentifie pour la session en cours."""

    user = create_guest_user()
    login(request, user)
    return user


def safe_next_url(request, fallback="home") -> str:
    """URL de retour fournie par la page appelante, si elle reste sur le site."""

    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback)


def guest_allowed(view):
    """Vue jouable sans compte : un anonyme passe par la porte d'entrée invité.

    On ne crée jamais l'invité en douce sur une simple visite : le compte
    n'apparaît qu'après un clic explicite, ce qui évite d'ouvrir un compte à
    chaque robot d'indexation qui suit un lien de partie.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view(request, *args, **kwargs)
        return render(
            request,
            "guest_gate.html",
            {"next": request.get_full_path()},
            status=200,
        )

    return wrapper


def members_only(view):
    """Réservé aux comptes complets : l'invité est renvoyé vers l'inscription."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if is_member(request.user):
            return view(request, *args, **kwargs)
        return render(
            request,
            "members_only.html",
            {
                "next": request.get_full_path(),
                "feature": getattr(view, "member_feature", None),
            },
            status=200,
        )

    return wrapper


def member_feature(label, promise):
    """Décrit ce que débloque une page réservée, pour la page d'invitation."""

    def decorate(view):
        view.member_feature = {"label": label, "promise": promise}
        return view

    return decorate


def guest_redirect(request, fallback="home"):
    """Redirection commune après ouverture d'une session invité."""

    return redirect(safe_next_url(request, fallback))
