from django.urls import path

from . import views

app_name = "islands"

urlpatterns = [
    path("", views.lobby, name="lobby"),
    path("api/lobby/state/", views.api_lobby_state, name="api_lobby_state"),
    path("games/create/", views.create_game, name="create_game"),
    path("games/<uuid:game_id>/join/", views.join_game, name="join_game"),
    path("games/<uuid:game_id>/", views.game_detail, name="game_detail"),
    path("api/games/<uuid:game_id>/state/", views.api_state, name="api_state"),
    path("api/games/<uuid:game_id>/bots/add/", views.api_add_bot, name="api_add_bot"),
    path(
        "api/games/<uuid:game_id>/bots/<int:bot_id>/remove/",
        views.api_remove_bot,
        name="api_remove_bot",
    ),
    path("api/games/<uuid:game_id>/start/", views.api_start, name="api_start"),
    path("api/games/<uuid:game_id>/place/", views.api_place, name="api_place"),
    path("api/games/<uuid:game_id>/ready/", views.api_ready, name="api_ready"),
    path("api/games/<uuid:game_id>/fire/", views.api_fire, name="api_fire"),
    path("api/games/<uuid:game_id>/bot-turn/", views.api_bot_turn, name="api_bot_turn"),
]
