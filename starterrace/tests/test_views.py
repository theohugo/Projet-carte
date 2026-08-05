import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from starterrace.models import Move
from starterrace.services import create_game, join_game, start_game
from starterrace.services import roll_dice as engine_roll

from .factories import FixedRng, make_starter_catalog, make_users


@override_settings(ROOT_URLCONF="starterrace.tests.urls")
class StarterRaceApiTests(TestCase):
    def setUp(self):
        make_starter_catalog()
        self.host, self.guest, self.outsider = make_users(3)
        self.game = create_game(self.host)
        join_game(self.game.id, self.guest)
        self.game = start_game(self.game.id, self.host)

    def post_json(self, name, user, payload):
        self.client.force_login(user)
        return self.client.post(
            reverse(f"starterrace:{name}", kwargs={"game_id": self.game.id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def fixed_roll(self, value):
        return patch(
            "starterrace.views.roll_dice",
            side_effect=lambda game_id, user, revision: engine_roll(
                game_id,
                user,
                revision,
                rng=FixedRng(value),
            ),
        )

    def test_state_requires_login_and_participation(self):
        url = reverse("starterrace:api_state", kwargs={"game_id": self.game.id})
        self.assertEqual(self.client.get(url).status_code, 302)

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_roll_then_move_endpoints_return_updated_state(self):
        with self.fixed_roll(6):
            rolled = self.post_json(
                "api_roll",
                self.host,
                {"expected_turn_revision": self.game.turn_revision},
            )

        self.assertEqual(rolled.status_code, 200)
        rolled_state = rolled.json()
        self.assertEqual(rolled_state["pending_roll"], 6)
        pawn_id = rolled_state["legal_pawn_ids"][0]

        moved = self.post_json(
            "api_move",
            self.host,
            {
                "pawn_id": pawn_id,
                "expected_turn_revision": rolled_state["turn_revision"],
            },
        )

        self.assertEqual(moved.status_code, 200)
        moved_state = moved.json()
        moved_pawn = next(
            pawn for player in moved_state["players"] for pawn in player["pawns"] if pawn["id"] == pawn_id
        )
        self.assertEqual(moved_pawn["position"], 0)
        self.assertTrue(moved_state["can_roll"])

    def test_duplicate_roll_returns_fresh_state_and_does_not_roll_twice(self):
        payload = {"expected_turn_revision": self.game.turn_revision}
        with self.fixed_roll(6):
            first = self.post_json("api_roll", self.host, payload)
            second = self.post_json("api_roll", self.host, payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "stale_revision")
        self.assertEqual(second.json()["state"]["pending_roll"], 6)
        self.assertFalse(Move.objects.exists())

    def test_json_validation_is_strict(self):
        bool_revision = self.post_json(
            "api_roll",
            self.host,
            {"expected_turn_revision": True},
        )
        bad_pawn = self.post_json(
            "api_move",
            self.host,
            {"expected_turn_revision": self.game.turn_revision, "pawn_id": "1"},
        )
        self.client.force_login(self.host)
        invalid_json = self.client.post(
            reverse("starterrace:api_roll", kwargs={"game_id": self.game.id}),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(bool_revision.status_code, 400)
        self.assertEqual(bad_pawn.status_code, 400)
        self.assertEqual(invalid_json.status_code, 400)

    def test_mutating_endpoints_reject_get(self):
        self.client.force_login(self.host)
        self.assertEqual(
            self.client.get(reverse("starterrace:api_roll", kwargs={"game_id": self.game.id})).status_code,
            405,
        )


@override_settings(ROOT_URLCONF="starterrace.tests.urls")
class StarterRacePagesTests(TestCase):
    def setUp(self):
        self.cards = make_starter_catalog()
        self.host, self.guest, self.outsider = make_users(3)

    def test_lobby_renders_official_starter_art_and_polling_contract(self):
        self.client.force_login(self.host)

        response = self.client.get(reverse("starterrace:lobby"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "starterrace/lobby.html")
        self.assertContains(response, "Course des Starters")
        self.assertContains(response, self.cards[0].sprite_url)
        self.assertContains(response, self.cards[3].sprite_url)
        self.assertContains(response, reverse("starterrace:api_lobby_state"))

    def test_participant_page_contains_state_roll_move_and_accessible_board_contract(self):
        game = create_game(self.host)
        join_game(game.id, self.guest)
        self.client.force_login(self.host)

        response = self.client.get(reverse("starterrace:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "starterrace/detail.html")
        self.assertContains(response, 'id="starterrace-game"')
        self.assertContains(response, reverse("starterrace:api_state", kwargs={"game_id": game.id}))
        self.assertContains(response, reverse("starterrace:api_roll", kwargs={"game_id": game.id}))
        self.assertContains(response, reverse("starterrace:api_move", kwargs={"game_id": game.id}))
        self.assertContains(response, 'aria-label="Piste commune de 40 cases"')

    def test_outsider_gets_join_invitation_for_an_open_game(self):
        game = create_game(self.host)
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("starterrace:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "join_invitation.html")
        self.assertContains(response, "Course des Starters")
        self.assertContains(response, reverse("starterrace:join_game", kwargs={"game_id": game.id}))

    def test_outsider_cannot_view_a_started_game(self):
        game = create_game(self.host)
        join_game(game.id, self.guest)
        start_game(game.id, self.host)
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("starterrace:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "join_invitation.html")
