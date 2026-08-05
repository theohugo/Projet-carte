from django.urls import path

from . import views

app_name = "starterrace"

urlpatterns = [
    path("", views.lobby, name="lobby"),
    path("api/lobby/state/", views.api_lobby_state, name="api_lobby_state"),
    path("games/create/", views.create_game_view, name="create_game"),
    path("games/<uuid:game_id>/join/", views.join_game_view, name="join_game"),
    path("games/<uuid:game_id>/bots/add/", views.add_bot_view, name="add_bot"),
    path(
        "games/<uuid:game_id>/bots/<int:player_id>/remove/",
        views.remove_bot_view,
        name="remove_bot",
    ),
    path("games/<uuid:game_id>/start/", views.start_game_view, name="start_game"),
    path("games/<uuid:game_id>/", views.game_detail, name="game_detail"),
    path("api/games/<uuid:game_id>/state/", views.api_state, name="api_state"),
    path("api/games/<uuid:game_id>/roll/", views.api_roll, name="api_roll"),
    path("api/games/<uuid:game_id>/move/", views.api_move, name="api_move"),
]
