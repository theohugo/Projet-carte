import json
from io import BytesIO
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from silhouette.services import create_game, current_round, join_game, start_game

from .factories import make_gen_one_catalog, make_users


def png_bytes(color=(255, 0, 0, 255)):
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGBA", (4, 4), color).save(buffer, format="PNG")
    return buffer.getvalue()


class RoundImageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        make_gen_one_catalog()
        self.host, self.guest, self.outsider = make_users(3)
        self.game = create_game(self.host, 5)
        join_game(self.game.id, self.guest)
        start_game(self.game.id, self.host)
        self.round = current_round(self.game)
        self.url = reverse("silhouette:round_image", args=[self.round.id])

    def fetch_image(self):
        response = mock.Mock(content=png_bytes(), status_code=200)
        response.raise_for_status = mock.Mock()
        with mock.patch("requests.get", return_value=response) as fetch:
            return self.client.get(self.url), fetch

    def test_the_image_is_reserved_to_the_players(self):
        self.client.force_login(self.outsider)

        response, _ = self.fetch_image()

        self.assertEqual(response.status_code, 403)

    def test_the_silhouette_hides_every_visible_pixel(self):
        from PIL import Image

        self.client.force_login(self.host)

        response, _ = self.fetch_image()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        with Image.open(BytesIO(response.content)) as image:
            colors = {pixel[:3] for pixel in image.convert("RGBA").getdata()}
        self.assertEqual(colors, {(12, 20, 34)})

    def test_the_real_artwork_comes_back_once_revealed(self):
        from PIL import Image

        self.round.revealed_at = self.round.started_at
        self.round.save(update_fields=["revealed_at"])
        self.client.force_login(self.host)

        response, _ = self.fetch_image()

        with Image.open(BytesIO(response.content)) as image:
            colors = {pixel[:3] for pixel in image.convert("RGBA").getdata()}
        self.assertEqual(colors, {(255, 0, 0)})

    def test_the_artwork_is_fetched_once_and_then_cached(self):
        self.client.force_login(self.host)

        _, first = self.fetch_image()
        _, second = self.fetch_image()

        self.assertEqual(first.call_count, 1)
        self.assertEqual(second.call_count, 0)

    def test_the_state_never_leaks_the_species_before_the_reveal(self):
        self.client.force_login(self.host)
        state_url = reverse("silhouette:api_state", args=[self.game.id])

        raw_payload = self.client.get(state_url).content.decode()
        payload = json.loads(raw_payload)

        # L'image passe par l'identifiant de la manche : ni le nom, ni le
        # Pokédex ID, ni l'URL du sprite ne transitent avant la révélation.
        self.assertEqual(payload["round"]["image_url"], f"/qui-est-ce-pokemon/rounds/{self.round.id}/image/")
        self.assertNotIn(self.round.pokemon_card.name_fr, raw_payload)
        self.assertNotIn(self.round.pokemon_card.sprite_url, raw_payload)
        self.assertNotIn("sprite_url", payload["round"])


class GuessEndpointTests(TestCase):
    def setUp(self):
        make_gen_one_catalog()
        self.host, self.outsider = make_users(2)
        self.game = create_game(self.host, 5)
        start_game(self.game.id, self.host)
        self.url = reverse("silhouette:api_guess", args=[self.game.id])

    def post(self, payload):
        return self.client.post(self.url, data=payload, content_type="application/json")

    def test_a_non_player_is_refused(self):
        self.client.force_login(self.outsider)

        response = self.post('{"text": "Pikachu"}')

        self.assertEqual(response.status_code, 403)

    def test_an_empty_guess_is_rejected(self):
        self.client.force_login(self.host)

        response = self.post('{"text": "   "}')

        self.assertEqual(response.status_code, 400)

    def test_a_stale_revision_returns_the_fresh_state(self):
        self.client.force_login(self.host)

        response = self.post('{"text": "Pikachu", "expected_turn_revision": 999}')

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_revision")

    def test_a_correct_guess_answers_with_the_updated_state(self):
        self.client.force_login(self.host)
        answer = current_round(self.game).pokemon_card.name_fr

        response = self.post(f'{{"text": "{answer}"}}')

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["is_correct"])
        self.assertGreater(payload["points"], 0)
        self.assertEqual(payload["state"]["players"][0]["score"], payload["points"])
