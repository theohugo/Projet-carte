import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from game.tests.i18n import LanguageIsolationMixin
from starterrace.models import Move
from starterrace.services import add_bot, create_game, join_game, start_game
from starterrace.services import advance_bot_step as engine_advance_bot_step
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
class StarterRacePagesTests(LanguageIsolationMixin, TestCase):
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

    def test_host_can_add_and_remove_a_bot_from_the_waiting_room(self):
        game = create_game(self.host)
        self.client.force_login(self.host)

        added = self.client.post(reverse("starterrace:add_bot", kwargs={"game_id": game.id}))
        bot = game.players.get(user__isnull=True)
        page = self.client.get(reverse("starterrace:game_detail", kwargs={"game_id": game.id}))
        removed = self.client.post(
            reverse(
                "starterrace:remove_bot",
                kwargs={"game_id": game.id, "player_id": bot.id},
            )
        )

        self.assertEqual(added.status_code, 302)
        self.assertContains(page, reverse("starterrace:add_bot", kwargs={"game_id": game.id}))
        self.assertContains(page, "data-remove-bot-url-template=")
        self.assertEqual(removed.status_code, 302)
        self.assertFalse(game.players.filter(user__isnull=True).exists())

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

    def test_browser_language_switches_template_js_and_pokemon_names(self):
        self.client.force_login(self.host)
        game = create_game(self.host)

        english = self.client.get(reverse("starterrace:lobby"), HTTP_ACCEPT_LANGUAGE="en")
        english_detail = self.client.get(
            reverse("starterrace:game_detail", kwargs={"game_id": game.id}),
            HTTP_ACCEPT_LANGUAGE="en",
        )
        french = self.client.get(reverse("starterrace:lobby"), HTTP_ACCEPT_LANGUAGE="fr")

        self.assertContains(english, "Starter Race")
        self.assertContains(english, "Create a race")
        self.assertContains(english, "Bulbasaur")
        self.assertContains(english, "Play Starter Race online on PokéTable")
        self.assertContains(english, "starterrace/css/starterrace.css?v=3")
        self.assertNotContains(english, "Créer une course")
        self.assertContains(english_detail, 'id="starterrace-i18n"')
        self.assertContains(english_detail, "Roll the die")
        self.assertContains(english_detail, "Live Starter Race table")
        self.assertContains(english_detail, "starterrace/js/game.js?v=4")
        self.assertContains(french, "Course des Starters")
        self.assertContains(french, "Créer une course")
        self.assertContains(french, "Bulbizarre")
        self.assertContains(french, "Joue à Course des Starters en ligne sur PokéTable")


@override_settings(ROOT_URLCONF="starterrace.tests.urls")
class StarterRaceBotApiTests(LanguageIsolationMixin, TestCase):
    def setUp(self):
        make_starter_catalog()
        self.host = make_users(1)[0]
        self.game = create_game(self.host)
        add_bot(self.game.id, self.host)
        self.game = start_game(self.game.id, self.host)
        self.client.force_login(self.host)

    def test_api_exposes_bot_rolls_and_moves_one_poll_at_a_time(self):
        bot_rng = FixedRng(6, 2)
        with (
            patch(
                "starterrace.views.roll_dice",
                side_effect=lambda game_id, user, revision: engine_roll(
                    game_id,
                    user,
                    revision,
                    rng=FixedRng(1),
                ),
            ),
            patch(
                "starterrace.views.advance_bot_step",
                side_effect=lambda game_id: engine_advance_bot_step(
                    game_id,
                    rng=bot_rng,
                ),
            ),
        ):
            response = self.client.post(
                reverse("starterrace:api_roll", kwargs={"game_id": self.game.id}),
                data=json.dumps({"expected_turn_revision": self.game.turn_revision}),
                content_type="application/json",
            )
            state_url = reverse("starterrace:api_state", kwargs={"game_id": self.game.id})
            first_roll = self.client.get(state_url)
            first_move = self.client.get(state_url)
            second_roll = self.client.get(state_url)
            second_move = self.client.get(state_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["current_turn"]["is_bot"])
        self.assertIsNone(payload["pending_roll"])
        self.assertEqual(first_roll.json()["pending_roll"], 6)
        self.assertEqual(first_move.json()["players"][1]["pawns"][0]["position"], 0)
        self.assertIsNone(first_move.json()["pending_roll"])
        self.assertEqual(second_roll.json()["pending_roll"], 2)
        self.assertEqual(second_move.json()["players"][1]["pawns"][0]["position"], 2)
        self.assertEqual(second_move.json()["current_turn"]["username"], self.host.username)
        self.assertEqual(list(Move.objects.values_list("roll", flat=True)), [1, 6, 2])

    def test_english_api_validation_error_is_localized(self):
        response = self.client.post(
            reverse("starterrace:api_roll", kwargs={"game_id": self.game.id}),
            data="{",
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON request.")
