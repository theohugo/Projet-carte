import json

from django.test import TestCase, override_settings
from django.urls import reverse

from islands.models import Shot
from islands.services import create_game, join_game

from .factories import make_catalog, make_users, ready_both


@override_settings(ROOT_URLCONF="islands.tests.urls")
class IslandApiTests(TestCase):
    def setUp(self):
        make_catalog()
        self.host, self.guest, self.outsider = make_users()
        self.game = create_game(self.host)
        self.game, _ = join_game(self.game.id, self.guest)

    def post_json(self, name, user, payload):
        self.client.force_login(user)
        return self.client.post(
            reverse(f"islands:{name}", kwargs={"game_id": self.game.id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_state_requires_login_and_participation(self):
        url = reverse("islands:api_state", kwargs={"game_id": self.game.id})
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_place_and_ready_api_return_personalized_state(self):
        formation = self.game.players.get(user=self.host).formations.get(slot=0)
        response = self.post_json(
            "api_place",
            self.host,
            {
                "formation_id": formation.id,
                "row": 0,
                "col": 0,
                "orientation": "H",
                "expected_turn_revision": self.game.turn_revision,
            },
        )

        self.assertEqual(response.status_code, 200)
        state = response.json()
        own = next(item for item in state["own_formations"] if item["id"] == formation.id)
        self.assertEqual(own["cells"], [[0, 0], [0, 1]])
        self.assertEqual(state["opponent_formations"], [])

        ready = self.post_json(
            "api_ready",
            self.host,
            {"expected_turn_revision": state["turn_revision"]},
        )
        self.assertEqual(ready.status_code, 400)
        self.assertIn("quatre Pokémon", ready.json()["error"])

    def test_stale_request_returns_409_with_fresh_private_state(self):
        formation = self.game.players.get(user=self.host).formations.get(slot=0)
        payload = {
            "formation_id": formation.id,
            "row": 0,
            "col": 0,
            "orientation": "H",
            "expected_turn_revision": self.game.turn_revision,
        }
        first = self.post_json("api_place", self.host, payload)
        second = self.post_json("api_place", self.host, payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "stale_revision")
        self.assertEqual(second.json()["state"]["opponent_formations"], [])

    def test_fire_endpoint_reports_result_and_rejects_duplicate(self):
        self.game = ready_both(self.game, self.host, self.guest)
        payload = {"row": 0, "col": 0, "expected_turn_revision": self.game.turn_revision}
        response = self.post_json("api_fire", self.host, payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action_result"]["result"], "HIT")
        self.assertEqual(response.json()["action_result"]["coordinate"], "A1")
        self.assertEqual(Shot.objects.count(), 1)

        guest_miss = self.post_json(
            "api_fire",
            self.guest,
            {"row": 6, "col": 7, "expected_turn_revision": response.json()["turn_revision"]},
        )
        duplicate = self.post_json(
            "api_fire",
            self.host,
            {"row": 0, "col": 0, "expected_turn_revision": guest_miss.json()["turn_revision"]},
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("déjà", duplicate.json()["error"])
        self.assertEqual(Shot.objects.count(), 2)

    def test_payload_validation_and_http_methods_are_strict(self):
        boolean_revision = self.post_json("api_ready", self.host, {"expected_turn_revision": True})
        invalid_json_url = reverse("islands:api_place", kwargs={"game_id": self.game.id})
        self.client.force_login(self.host)
        invalid_json = self.client.post(invalid_json_url, data="{", content_type="application/json")
        get_mutation = self.client.get(reverse("islands:api_fire", kwargs={"game_id": self.game.id}))

        self.assertEqual(boolean_revision.status_code, 400)
        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(get_mutation.status_code, 405)

    def test_lobby_poll_lists_open_and_personal_games(self):
        self.client.force_login(self.host)
        response = self.client.get(reverse("islands:api_lobby_state"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["open_games"], [])
        self.assertIn(str(self.game.id), response.json()["my_game_ids"])
        self.assertEqual(response.json()["my_games"][0]["player_count"], 2)


@override_settings(ROOT_URLCONF="islands.tests.urls")
class IslandPageTests(TestCase):
    def setUp(self):
        make_catalog()
        self.host, self.guest, self.outsider = make_users()

    def test_lobby_contains_real_artwork_rules_and_polling_contract(self):
        self.client.force_login(self.host)
        response = self.client.get(reverse("islands:lobby"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "islands/lobby.html")
        self.assertContains(response, "Bataille")
        self.assertContains(response, "official-artwork")
        self.assertContains(response, reverse("islands:api_lobby_state"))
        self.assertContains(response, "Grille 8 × 8")

    def test_participant_page_exposes_all_four_api_urls_and_accessible_grid(self):
        game = create_game(self.host)
        join_game(game.id, self.guest)
        self.client.force_login(self.host)
        response = self.client.get(reverse("islands:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "islands/detail.html")
        for name in ("api_state", "api_place", "api_ready", "api_fire"):
            self.assertContains(response, reverse(f"islands:{name}", kwargs={"game_id": game.id}))
        self.assertContains(response, 'role="grid"')
        self.assertContains(response, "Utilise les flèches")

    def test_outsider_can_accept_open_invitation_but_not_view_closed_one(self):
        game = create_game(self.host)
        self.client.force_login(self.outsider)
        invitation = self.client.get(reverse("islands:game_detail", kwargs={"game_id": game.id}))
        self.assertEqual(invitation.status_code, 200)
        self.assertTemplateUsed(invitation, "join_invitation.html")
        self.assertContains(invitation, reverse("islands:join_game", kwargs={"game_id": game.id}))

        joined = self.client.post(reverse("islands:join_game", kwargs={"game_id": game.id}))
        self.assertRedirects(joined, reverse("islands:game_detail", kwargs={"game_id": game.id}))
        self.assertTrue(game.players.filter(user=self.outsider).exists())

        self.client.force_login(self.guest)
        closed = self.client.get(reverse("islands:game_detail", kwargs={"game_id": game.id}))
        self.assertEqual(closed.status_code, 403)
        self.assertContains(closed, "Invitation expirée", status_code=403)
