"""Contexte commun à tous les gabarits."""

from game.guests import is_guest, is_member


def account_state(request):
    """Expose l'état du compte : invité, membre, ou simple visiteur.

    Les cadenas et les appels à créer un compte apparaissent dans la navigation
    et sur l'accueil : sans ce contexte, chaque gabarit devrait refaire le test.
    """

    user = getattr(request, "user", None)
    return {
        "is_guest": is_guest(user),
        "is_member": is_member(user),
    }
