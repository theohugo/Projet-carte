import json

from django.test import TestCase
from django.urls import reverse

from game.tests.i18n import LanguageIsolationMixin
from pictionary.models import PictionaryStroke
from pictionary.services import create_game, current_round, join_game, start_game
from silhouette.services import create_game as create_silhouette_game
from silhouette.tests.factories import make_gen_one_catalog, make_users


class PictionaryEndpointTests(LanguageIsolationMixin, TestCase):
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

    def test_accept_language_localizes_invalid_json_and_business_errors(self):
        stroke_url = reverse("pictionary:api_stroke", args=[self.game.id])
        self.client.force_login(self.host)
        invalid_json = self.client.post(
            stroke_url,
            data="not json",
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="en-US",
        )

        self.client.force_login(self.guest)
        forbidden_stroke = self.client.post(
            stroke_url,
            data=json.dumps({"points": [[0.2, 0.2], [0.3, 0.3]]}),
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="en-US",
        )

        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(invalid_json.json()["error"], "Invalid JSON request.")
        self.assertEqual(forbidden_stroke.status_code, 403)
        self.assertEqual(forbidden_stroke.json()["error"], "Only the drawer can draw.")

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

    def test_accept_language_localizes_the_drawers_word(self):
        card = current_round(self.game).pokemon_card
        card.name_fr = "Bulbizarre"
        card.name_en = "Bulbasaur"
        card.save(update_fields=["name_fr", "name_en"])
        self.client.force_login(self.host)
        url = reverse("pictionary:api_state", args=[self.game.id])

        french = self.client.get(url, HTTP_ACCEPT_LANGUAGE="fr").json()
        english = self.client.get(url, HTTP_ACCEPT_LANGUAGE="en-US").json()

        self.assertEqual(french["language"], "fr")
        self.assertEqual(french["round"]["word"], "Bulbizarre")
        self.assertEqual(english["language"], "en")
        self.assertEqual(english["round"]["word"], "Bulbasaur")

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


class LobbyPageTests(LanguageIsolationMixin, TestCase):
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

    def test_accept_language_renders_both_lobbies_in_english(self):
        silhouette_response = self.client.get(reverse("silhouette:lobby"), HTTP_ACCEPT_LANGUAGE="en")
        pictionary_response = self.client.get(reverse("pictionary:lobby"), HTTP_ACCEPT_LANGUAGE="en")

        self.assertContains(silhouette_response, "Open a room")
        self.assertContains(silhouette_response, "Who’s That Pokémon?")
        self.assertNotContains(silhouette_response, "Ouvrir un salon")
        self.assertContains(pictionary_response, "Drawing · guessing")
        self.assertContains(pictionary_response, "Open rooms")
        self.assertNotContains(pictionary_response, "Salons ouverts")

    def test_anonymous_visitors_can_read_both_lobbies_and_live_states(self):
        pictionary_game = create_game(self.user, 3)
        silhouette_game = create_silhouette_game(self.user, 5)
        self.client.logout()

        cases = (
            (
                "pictionary:lobby",
                "pictionary:api_lobby_state",
                "pictionary:create_game",
                "pictionary:join_game",
                pictionary_game.id,
            ),
            (
                "silhouette:lobby",
                "silhouette:api_lobby_state",
                "silhouette:create_game",
                "silhouette:join_game",
                silhouette_game.id,
            ),
        )
        for lobby_name, state_name, create_name, join_name, game_id in cases:
            with self.subTest(lobby=lobby_name):
                page = self.client.get(reverse(lobby_name))
                state = self.client.get(reverse(state_name))

                self.assertEqual(page.status_code, 200)
                self.assertEqual(state.status_code, 200)
                open_game = next(entry for entry in state.json()["open_games"] if entry["id"] == str(game_id))
                self.assertFalse(open_game["is_mine"])
                self.assertContains(page, f'action="{reverse(create_name)}"', html=False)
                self.assertContains(
                    page,
                    f'action="{reverse(join_name, args=[game_id])}"',
                    html=False,
                )

                joined = self.client.post(reverse(join_name, args=[game_id]))
                self.assertEqual(joined.status_code, 302)
                self.assertNotIn("/accounts/login/", joined.url)
                self.client.logout()

    def test_creating_a_game_lands_on_its_page(self):
        response = self.client.post(reverse("silhouette:create_game"), {"round_count": 15})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/qui-est-ce-pokemon/games/", response.url)
