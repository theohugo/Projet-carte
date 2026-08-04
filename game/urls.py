from django.urls import path

from game import api, views


urlpatterns = [
    # Accueil et jeux
    path("", views.hub, name="home"),
    path("uno/", views.lobby, name="lobby"),

    # Authentification
    path("signup/", views.signup, name="signup"),

    # Profils
    path(
        "profil/",
        views.my_profile,
        name="my_profile",
    ),
    path(
        "profil/modifier/",
        views.edit_profile,
        name="edit_profile",
    ),
    path(
        "joueurs/<str:username>/",
        views.public_profile,
        name="public_profile",
    ),

    # Amis
    path(
        "amis/",
        views.friends,
        name="friends",
    ),
    path(
        "amis/rechercher/",
        views.player_search,
        name="player_search",
    ),
    path(
        "amis/demander/<str:username>/",
        views.send_friend_request,
        name="send_friend_request",
    ),
    path(
        "amis/<int:friendship_id>/accepter/",
        views.accept_friend_request,
        name="accept_friend_request",
    ),
    path(
        "amis/<int:friendship_id>/refuser/",
        views.reject_friend_request,
        name="reject_friend_request",
    ),
    path(
        "amis/<int:friendship_id>/annuler/",
        views.cancel_friend_request,
        name="cancel_friend_request",
    ),
    path(
        "amis/<int:friendship_id>/supprimer/",
        views.remove_friend,
        name="remove_friend",
    ),

    # Parties Poké-Uno
    path(
        "games/<uuid:game_id>/",
        views.game_detail,
        name="game_detail",
    ),
    path(
        "games/<uuid:game_id>/join/",
        views.join_game,
        name="join_game",
    ),
    path(
        "games/<uuid:game_id>/start/",
        views.start_game_view,
        name="start_game",
    ),
    path(
        "games/<uuid:game_id>/bots/add/",
        views.add_bot_view,
        name="add_bot",
    ),
    path(
        "games/<uuid:game_id>/bots/<int:player_id>/remove/",
        views.remove_bot_view,
        name="remove_bot",
    ),

    # API du lobby et des parties
    path(
        "api/lobby/state/",
        api.api_lobby_state,
        name="api_lobby_state",
    ),
    path(
        "api/games/<uuid:game_id>/state/",
        api.api_game_state,
        name="api_game_state",
    ),
    path(
        "api/games/<uuid:game_id>/start/",
        api.api_start_game,
        name="api_start_game",
    ),
    path(
        "api/games/<uuid:game_id>/play/",
        api.api_play_card,
        name="api_play_card",
    ),
    path(
        "api/games/<uuid:game_id>/draw/",
        api.api_draw_card,
        name="api_draw_card",
    ),
    path(
        "api/games/<uuid:game_id>/bot-turn/",
        api.api_bot_turn,
        name="api_bot_turn",
    ),
]