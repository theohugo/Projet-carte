from django.urls import path

from game import api, views

urlpatterns = [
    path("", views.lobby, name="lobby"),
    path("signup/", views.signup, name="signup"),
    path("games/<uuid:game_id>/", views.game_detail, name="game_detail"),
    path("games/<uuid:game_id>/join/", views.join_game, name="join_game"),
    path("games/<uuid:game_id>/start/", views.start_game_view, name="start_game"),
    path("api/games/<uuid:game_id>/state/", api.api_game_state, name="api_game_state"),
    path("api/games/<uuid:game_id>/play/", api.api_play_card, name="api_play_card"),
    path("api/games/<uuid:game_id>/draw/", api.api_draw_card, name="api_draw_card"),
]
