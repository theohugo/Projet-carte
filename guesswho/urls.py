from django.urls import path

from . import views

app_name = "guesswho"

urlpatterns = [
    path("", views.lobby, name="lobby"),
    path("api/lobby/state/", views.api_lobby_state, name="api_lobby_state"),
    path("games/create/", views.create_game, name="create_game"),
    path("games/<uuid:game_id>/join/", views.join_game, name="join_game"),
    path("games/<uuid:game_id>/", views.game_detail, name="game_detail"),
    path("api/games/<uuid:game_id>/state/", views.api_state, name="api_state"),
    path(
        "api/games/<uuid:game_id>/choose/",
        views.api_choose_target,
        name="api_choose_target",
    ),
    path(
        "api/games/<uuid:game_id>/ask/",
        views.api_ask_question,
        name="api_ask_question",
    ),
    path(
        "api/games/<uuid:game_id>/answer/",
        views.api_answer_question,
        name="api_answer_question",
    ),
    path("api/games/<uuid:game_id>/guess/", views.api_guess, name="api_guess"),
    path(
        "api/games/<uuid:game_id>/cards/reset/",
        views.api_reset_candidates,
        name="api_reset_candidates",
    ),
    path(
        "api/games/<uuid:game_id>/cards/<int:pokemon_card_id>/toggle/",
        views.api_toggle_candidate,
        name="api_toggle_candidate",
    ),
]
