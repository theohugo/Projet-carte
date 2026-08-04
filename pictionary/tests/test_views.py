import json

from django.test import TestCase
from django.urls import reverse

from pictionary.models import PictionaryStroke
from pictionary.services import create_game, current_round, join_game, start_game
from silhouette.tests.factories import make_gen_one_catalog, make_users


class PictionaryEndpointTests(TestCase):
    def setUp(self):
        make_gen_one_catalog()
        self.host, self.guest, self.outsider = make_users(3)
        self.game = create_game(self.host, 3)
        join_game(self.game.id, self.guest)
        start_game(self.game.id, self.host)

    def post(self, name, payload, user):
        self.client.force_login(user)
        return self.client.post(
            reverse(name, args=[self.game.id]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_a_non_player_cannot_read_the_state(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("pictionary:api_state", args=[self.game.id]))

        self.assertEqual(response.status_code, 403)

    def test_a_guesser_cannot_post_strokes(self):
        response = self.post("pictionary:api_stroke", {"points": [[0.2, 0.2]]}, self.guest)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PictionaryStroke.objects.exists())

    def test_the_drawer_posts_a_stroke_and_gets_its_sequence(self):
        response = self.post("pictionary:api_stroke", {"points": [[0.2, 0.2], [0.3, 0.3]]}, self.host)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sequence"], 1)

    def test_an_invalid_json_body_is_rejected(self):
        self.client.force_login(self.host)

        response = self.client.post(
            reverse("pictionary:api_stroke", args=[self.game.id]),
            data="pas du json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_the_state_only_sends_new_strokes(self):
        self.post("pictionary:api_stroke", {"points": [[0.1, 0.1]]}, self.host)
        self.post("pictionary:api_stroke", {"points": [[0.5, 0.5]]}, self.host)
        self.client.force_login(self.guest)

        url = reverse("pictionary:api_state", args=[self.game.id])
        payload = self.client.get(f"{url}?since=1").json()

        self.assertEqual([stroke["sequence"] for stroke in payload["round"]["strokes"]], [2])

    def test_the_guesser_state_never_carries_the_word(self):
        self.client.force_login(self.guest)

        raw = self.client.get(reverse("pictionary:api_state", args=[self.game.id])).content.decode()

        self.assertNotIn(current_round(self.game).pokemon_card.name_fr, raw)

    def test_a_correct_guess_returns_the_updated_state(self):
        answer = current_round(self.game).pokemon_card.name_fr

        response = self.post("pictionary:api_guess", {"text": answer}, self.guest)

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["is_correct"])
        self.assertGreater(payload["points"], 0)

    def test_a_stale_revision_returns_the_fresh_state(self):
        response = self.post(
            "pictionary:api_guess",
            {"text": "Pikachu", "expected_turn_revision": 999},
            self.guest,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_revision")


class LobbyPageTests(TestCase):
    def setUp(self):
        make_gen_one_catalog()
        (self.user,) = make_users(1)
        self.client.force_login(self.user)

    def test_both_new_games_are_offered_on_the_hub(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Qui est ce Pokémon ?")
        self.assertContains(response, "Pictionary Pokémon")
        self.assertContains(response, reverse("silhouette:lobby"))
        self.assertContains(response, reverse("pictionary:lobby"))

    def test_the_pictionary_lobby_offers_the_three_lengths(self):
        response = self.client.get(reverse("pictionary:lobby"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3 manches")
        self.assertContains(response, "6 manches")
        self.assertContains(response, "9 manches")

    def test_the_silhouette_lobby_offers_the_three_lengths(self):
        response = self.client.get(reverse("silhouette:lobby"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "5 manches")
        self.assertContains(response, "10 manches")
        self.assertContains(response, "15 manches")

    def test_creating_a_game_lands_on_its_page(self):
        response = self.client.post(reverse("silhouette:create_game"), {"round_count": 15})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/qui-est-ce-pokemon/games/", response.url)
