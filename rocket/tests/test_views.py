import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from game.tests.i18n import LanguageIsolationMixin
from rocket.services import create_game, join_game

User = get_user_model()


class RocketViewTests(LanguageIsolationMixin, TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="pw")
        self.outsider = User.objects.create_user(username="outsider", password="pw")
        self.game = create_game(self.host)

    def test_anonymous_lobby_is_public_without_creating_a_guest(self):
        response = self.client.get(reverse("rocket:lobby"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "rocket/lobby.html")
        self.assertTemplateNotUsed(response, "guest_gate.html")
        self.assertContains(response, "Infiltration Rocket")
        self.assertEqual(User.objects.count(), 2)

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

    def test_browser_language_localizes_lobby_detail_and_js_catalog(self):
        self.client.force_login(self.host)

        english_lobby = self.client.get(reverse("rocket:lobby"), HTTP_ACCEPT_LANGUAGE="en")
        english_detail = self.client.get(
            reverse("rocket:game_detail", kwargs={"game_id": self.game.id}),
            HTTP_ACCEPT_LANGUAGE="en",
        )
        french_lobby = self.client.get(reverse("rocket:lobby"), HTTP_ACCEPT_LANGUAGE="fr")

        self.assertContains(english_lobby, "Team Rocket Infiltration")
        self.assertContains(english_lobby, "Create an infiltration")
        self.assertContains(english_lobby, "Play Team Rocket Infiltration on PokéTable")
        self.assertContains(english_lobby, "rocket/css/rocket.css?v=3")
        self.assertNotContains(english_lobby, "Créer une infiltration")
        self.assertContains(english_detail, 'class="rocket-document"')
        self.assertContains(english_detail, 'class="rocket-shell"')
        self.assertContains(english_detail, 'id="rocket-i18n"')
        self.assertContains(english_detail, "Choose a target to sabotage")
        self.assertContains(english_detail, "Live Team Rocket Infiltration mission")
        self.assertContains(english_detail, "rocket/js/game.js?v=3")
        self.assertContains(french_lobby, "Créer une infiltration")
        self.assertContains(french_lobby, "Joue à Infiltration Rocket sur PokéTable")

    def test_invalid_json_error_is_english_for_an_english_browser(self):
        self.client.force_login(self.host)
        response = self.client.post(
            reverse("rocket:api_vote", kwargs={"game_id": self.game.id}),
            data="not-json",
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON request.")
