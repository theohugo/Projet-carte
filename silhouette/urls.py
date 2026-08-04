from django.urls import path

from . import views

app_name = "silhouette"

urlpatterns = [
    path("", views.lobby, name="lobby"),
    path("api/lobby/state/", views.api_lobby_state, name="api_lobby_state"),
    path("games/create/", views.create_game_view, name="create_game"),
    path("games/<uuid:game_id>/join/", views.join_game_view, name="join_game"),
    path("games/<uuid:game_id>/start/", views.start_game_view, name="start_game"),
    path("games/<uuid:game_id>/", views.game_detail, name="game_detail"),
    path("api/games/<uuid:game_id>/state/", views.api_state, name="api_state"),
    path("api/games/<uuid:game_id>/guess/", views.api_guess, name="api_guess"),
    path("rounds/<int:round_id>/image/", views.round_image, name="round_image"),
]
