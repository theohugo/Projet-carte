"""Enregistrement commun d'une fin de partie multijoueur."""

from django.db.models import F

from game.models import Profile
from game.quests import EVENT_GAME_PLAYED, EVENT_GAME_WON, record_event


def record_completed_game(users, winner_user_ids) -> None:
    """Met à jour statistiques et quêtes une seule fois, au moment de la fin.

    Les moteurs restent responsables de n'appeler cette fonction qu'au passage
    vers leur état terminal ; la mise à jour groupée évite les compteurs perdus
    lorsque plusieurs parties se terminent simultanément.
    """

    users = list(users)
    user_ids = {user.pk for user in users}
    winners = set(winner_user_ids) & user_ids
    Profile.objects.filter(user_id__in=user_ids).update(total_games_played=F("total_games_played") + 1)
    Profile.objects.filter(user_id__in=winners).update(total_games_won=F("total_games_won") + 1)
    for user in users:
        record_event(user, EVENT_GAME_PLAYED)
        if user.pk in winners:
            record_event(user, EVENT_GAME_WON)
