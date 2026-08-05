import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from metamorph.models import MetamorphMove
from metamorph.services import PAIR_COUNT, create_game, join_game, start_game

from .factories import make_catalog, make_users


@override_settings(ROOT_URLCONF="metamorph.tests.urls")
class MetamorphViewTests(TestCase):
    def setUp(self):
        self.species, self.ditto = make_catalog()
        self.users = make_users(3)
        self.host, self.guest, self.outsider = self.users

    def make_waiting_game(self):
        game = create_game(self.host)
        game, _ = join_game(game.id, self.guest)
        return game

    def start_deterministically(self, game):
        with (
            patch("metamorph.services.random.sample", return_value=self.species[:PAIR_COUNT]),
            patch("metamorph.services.random.shuffle", side_effect=lambda deck: None),
        ):
            return start_game(game.id, self.host, game.turn_revision)

    def post_json(self, name, user, game, payload):
        self.client.force_login(user)
        return self.client.post(
            reverse(f"metamorph:{name}", kwargs={"game_id": game.id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_lobby_renders_integrated_page_and_live_endpoint(self):
        self.client.force_login(self.host)
        response = self.client.get(reverse("metamorph:lobby"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "metamorph/lobby.html")
        self.assertContains(response, "Métamorph Mystère")
        self.assertContains(response, self.ditto.sprite_url)
        self.assertContains(response, reverse("metamorph:api_lobby_state"))
        self.assertContains(response, reverse("home"))

    def test_anonymous_visitors_can_read_the_lobby_and_public_state(self):
        game = create_game(self.host)

        page = self.client.get(reverse("metamorph:lobby"))
        state = self.client.get(reverse("metamorph:api_lobby_state"))

        self.assertEqual(page.status_code, 200)
        self.assertTemplateUsed(page, "metamorph/lobby.html")
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()["my_games"], [])
        self.assertEqual(state.json()["my_game_ids"], [])
        self.assertIn(str(game.id), [entry["id"] for entry in state.json()["open_games"]])
        self.assertContains(page, f'action="{reverse("metamorph:create_game")}"', html=False)
        self.assertContains(
            page,
            f'action="{reverse("metamorph:join_game", kwargs={"game_id": game.id})}"',
            html=False,
        )

        joined = self.client.post(reverse("metamorph:join_game", kwargs={"game_id": game.id}))
        self.assertRedirects(joined, reverse("metamorph:game_detail", kwargs={"game_id": game.id}))
        self.assertTrue(game.players.filter(user__profile__is_guest=True).exists())

    def test_create_and_join_are_post_only(self):
        self.client.force_login(self.host)
        create_url = reverse("metamorph:create_game")
        self.assertEqual(self.client.get(create_url).status_code, 405)
        response = self.client.post(create_url)
        self.assertEqual(response.status_code, 302)

        game = create_game(self.host)
        self.client.force_login(self.guest)
        join_url = reverse("metamorph:join_game", kwargs={"game_id": game.id})
        self.assertEqual(self.client.get(join_url).status_code, 405)
        response = self.client.post(join_url)
        self.assertRedirects(
            response,
            reverse("metamorph:game_detail", kwargs={"game_id": game.id}),
        )

    def test_nonparticipant_gets_invitation_then_closed_table_is_forbidden(self):
        game = self.make_waiting_game()
        self.client.force_login(self.outsider)
        detail_url = reverse("metamorph:game_detail", kwargs={"game_id": game.id})

        invitation = self.client.get(detail_url)
        self.assertEqual(invitation.status_code, 200)
        self.assertTemplateUsed(invitation, "join_invitation.html")
        self.assertContains(
            invitation,
            reverse("metamorph:join_game", kwargs={"game_id": game.id}),
        )

        game = self.start_deterministically(game)
        forbidden = self.client.get(detail_url)
        self.assertEqual(forbidden.status_code, 403)
        self.assertContains(forbidden, "Invitation expirée", status_code=403)

    def test_detail_exposes_only_own_app_endpoints_and_initial_state(self):
        game = self.make_waiting_game()
        self.client.force_login(self.host)
        response = self.client.get(reverse("metamorph:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "metamorph/detail.html")
        self.assertContains(response, 'id="metamorph-game"')
        self.assertContains(response, reverse("metamorph:api_state", kwargs={"game_id": game.id}))
        self.assertContains(response, reverse("metamorph:api_start", kwargs={"game_id": game.id}))
        self.assertContains(response, reverse("metamorph:api_draw", kwargs={"game_id": game.id}))
        self.assertContains(response, reverse("metamorph:api_add_bot", kwargs={"game_id": game.id}))
        self.assertContains(response, reverse("metamorph:api_bot_turn", kwargs={"game_id": game.id}))

    def test_host_manages_a_bot_and_api_plays_its_turn(self):
        game = create_game(self.host)
        added = self.post_json(
            "api_add_bot",
            self.host,
            game,
            {"expected_turn_revision": game.turn_revision},
        )
        self.assertEqual(added.status_code, 200)
        bot = next(player for player in added.json()["players"] if player["is_bot"])

        with (
            patch("metamorph.services.random.sample", return_value=self.species[:PAIR_COUNT]),
            patch("metamorph.services.random.shuffle", side_effect=lambda deck: None),
        ):
            started = self.post_json(
                "api_start",
                self.host,
                game,
                {"expected_turn_revision": added.json()["turn_revision"]},
            )
        drawn = self.post_json(
            "api_draw",
            self.host,
            game,
            {
                "card_position": 1,
                "expected_turn_revision": started.json()["turn_revision"],
            },
        )
        self.assertEqual(drawn.status_code, 200)
        self.assertEqual(drawn.json()["current_turn"]["id"], bot["id"])

        with patch("metamorph.services.random.randint", return_value=1):
            played = self.post_json(
                "api_bot_turn",
                self.host,
                game,
                {"expected_turn_revision": drawn.json()["turn_revision"]},
            )
        self.assertEqual(played.status_code, 200)
        self.assertTrue(played.json()["moves"][-1]["actor"]["is_bot"])

    def test_state_requires_login_and_participation(self):
        game = self.make_waiting_game()
        url = reverse("metamorph:api_state", kwargs={"game_id": game.id})
        self.assertEqual(self.client.get(url).status_code, 302)

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_host_starts_then_draws_through_json_endpoints(self):
        game = self.make_waiting_game()
        with (
            patch("metamorph.services.random.sample", return_value=self.species[:PAIR_COUNT]),
            patch("metamorph.services.random.shuffle", side_effect=lambda deck: None),
        ):
            started = self.post_json(
                "api_start",
                self.host,
                game,
                {"expected_turn_revision": game.turn_revision},
            )

        self.assertEqual(started.status_code, 200)
        started_state = started.json()
        self.assertEqual(started_state["status"], "EN_COURS")
        self.assertTrue(started_state["can_draw"])
        self.assertEqual(len(started_state["draw_source"]["hidden_cards"]), PAIR_COUNT)

        drawn = self.post_json(
            "api_draw",
            self.host,
            game,
            {
                "card_position": 1,
                "expected_turn_revision": started_state["turn_revision"],
            },
        )
        self.assertEqual(drawn.status_code, 200)
        self.assertTrue(drawn.json()["moves"][-1]["formed_pair"])
        self.assertEqual(MetamorphMove.objects.filter(game=game).count(), 1)

    def test_duplicate_draw_returns_409_with_fresh_private_state(self):
        game = self.start_deterministically(self.make_waiting_game())
        payload = {
            "card_position": 1,
            "expected_turn_revision": game.turn_revision,
        }
        first = self.post_json("api_draw", self.host, game, payload)
        second = self.post_json("api_draw", self.host, game, payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "stale_revision")
        self.assertEqual(
            second.json()["state"]["turn_revision"],
            first.json()["turn_revision"],
        )
        self.assertEqual(MetamorphMove.objects.filter(game=game).count(), 1)

    def test_api_never_serializes_opponent_hand_contents(self):
        game = self.start_deterministically(self.make_waiting_game())
        self.client.force_login(self.guest)
        response = self.client.get(reverse("metamorph:api_state", kwargs={"game_id": game.id}))
        state = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(state["me"]["hand"])
        host_payload = next(player for player in state["players"] if player["username"] == self.host.username)
        self.assertNotIn("hand", host_payload)
        self.assertNotIn("pokemon", host_payload)
        self.assertEqual(state["draw_source"]["hidden_cards"], [])

    def test_json_validation_and_http_methods_are_strict(self):
        game = self.start_deterministically(self.make_waiting_game())
        self.client.force_login(self.host)
        draw_url = reverse("metamorph:api_draw", kwargs={"game_id": game.id})

        self.assertEqual(self.client.get(draw_url).status_code, 405)
        malformed = self.client.post(draw_url, data="{", content_type="application/json")
        bool_revision = self.post_json(
            "api_draw",
            self.host,
            game,
            {"card_position": 1, "expected_turn_revision": True},
        )
        bool_position = self.post_json(
            "api_draw",
            self.host,
            game,
            {"card_position": True, "expected_turn_revision": game.turn_revision},
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(bool_revision.status_code, 400)
        self.assertEqual(bool_position.status_code, 400)

    def test_mutation_endpoints_enforce_csrf(self):
        game = self.make_waiting_game()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.host)
        detail_url = reverse("metamorph:game_detail", kwargs={"game_id": game.id})
        csrf_client.get(detail_url)
        start_url = reverse("metamorph:api_start", kwargs={"game_id": game.id})
        payload = json.dumps({"expected_turn_revision": game.turn_revision})

        refused = csrf_client.post(start_url, data=payload, content_type="application/json")
        self.assertEqual(refused.status_code, 403)

        token = csrf_client.cookies["csrftoken"].value
        with (
            patch("metamorph.services.random.sample", return_value=self.species[:PAIR_COUNT]),
            patch("metamorph.services.random.shuffle", side_effect=lambda deck: None),
        ):
            accepted = csrf_client.post(
                start_url,
                data=payload,
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            )
        self.assertEqual(accepted.status_code, 200)
