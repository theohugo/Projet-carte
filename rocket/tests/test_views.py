import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rocket.services import create_game, join_game

User = get_user_model()


class RocketViewTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="pw")
        self.outsider = User.objects.create_user(username="outsider", password="pw")
        self.game = create_game(self.host)

    def test_anonymous_lobby_uses_guest_gate(self):
        response = self.client.get(reverse("rocket:lobby"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "guest_gate.html")

    def test_authenticated_user_can_create_room(self):
        self.client.force_login(self.outsider)
        response = self.client.post(reverse("rocket:create_game"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/infiltration-rocket/games/", response.url)

    def test_non_participant_sees_join_page_without_private_state(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("rocket:game_detail", kwargs={"game_id": self.game.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "join_invitation.html")
        self.assertNotContains(response, "Dossier confidentiel")

    def test_api_state_rejects_outsider(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("rocket:api_state", kwargs={"game_id": self.game.id}))
        self.assertEqual(response.status_code, 403)

    def test_join_endpoint_adds_player(self):
        self.client.force_login(self.outsider)
        response = self.client.post(reverse("rocket:join_game", kwargs={"game_id": self.game.id}))
        self.assertRedirects(response, reverse("rocket:game_detail", kwargs={"game_id": self.game.id}))
        self.assertTrue(self.game.players.filter(user=self.outsider).exists())

    def test_invalid_json_is_rejected(self):
        join_game(self.game.id, self.outsider)
        self.client.force_login(self.outsider)
        response = self.client.post(
            reverse("rocket:api_vote", kwargs={"game_id": self.game.id}),
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_night_action_returns_rule_error_as_json(self):
        join_game(self.game.id, self.outsider)
        self.client.force_login(self.outsider)
        response = self.client.post(
            reverse("rocket:api_night_action", kwargs={"game_id": self.game.id}),
            data=json.dumps({"target_id": 999}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())
