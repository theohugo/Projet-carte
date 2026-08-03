import json

from django.test import Client, TestCase
from django.urls import reverse

from game.game_engine import GameEngine
from game.models import Game
from game.tests.factories import make_cards, make_game, make_types, make_users


class AnonymousAccessTests(TestCase):
    def test_lobby_redirects_anonymous_to_login(self):
        response = self.client.get(reverse("lobby"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_game_detail_redirects_anonymous_to_login(self):
        (user,) = make_users(1)
        game = make_game(user)
        response = self.client.get(reverse("game_detail", args=[game.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class LobbyTests(TestCase):
    def setUp(self):
        self.user = make_users(1)[0]
        self.client.force_login(self.user)

    def test_create_game_via_post(self):
        response = self.client.post(reverse("lobby"))
        self.assertEqual(Game.objects.count(), 1)
        game = Game.objects.first()
        self.assertTrue(game.players.filter(user=self.user).exists())
        self.assertRedirects(response, reverse("game_detail", args=[game.id]))


class PermissionTests(TestCase):
    def setUp(self):
        self.owner, self.outsider = make_users(2)
        self.game = make_game(self.owner)
        GameEngine(self.game).add_player(self.owner)

    def test_non_participant_cannot_view_game_detail(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("game_detail", args=[self.game.id]))
        self.assertEqual(response.status_code, 403)

    def test_non_participant_cannot_read_game_state(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("api_game_state", args=[self.game.id]))
        self.assertEqual(response.status_code, 403)

    def test_only_creator_can_start_game(self):
        second = make_users(1)[0]
        GameEngine(self.game).add_player(second)
        self.client.force_login(second)
        response = self.client.post(reverse("start_game", args=[self.game.id]))
        self.assertEqual(response.status_code, 403)


class GameStateApiSecurityTests(TestCase):
    """La règle anti-fuite vit dans le moteur (get_game_state), mais on la
    vérifie ici bout en bout via l'endpoint HTTP réellement exposé."""

    def setUp(self):
        self.types = make_types()
        self.cards = make_cards(self.types)
        self.p1_user, self.p2_user = make_users(2)
        self.game = make_game(self.p1_user)
        engine = GameEngine(self.game)
        self.gp1 = engine.add_player(self.p1_user)
        self.gp2 = engine.add_player(self.p2_user)
        engine.build_deck()
        # Distribution manuelle minimale pour avoir une main non vide côté p1.
        from game.models import GameCard

        first_p1_card = GameCard.objects.filter(game=self.game, location=GameCard.Location.PIOCHE).first()
        first_p1_card.location = GameCard.Location.MAIN
        first_p1_card.owner = self.gp1
        first_p1_card.save()

        self.game.status = Game.Status.EN_COURS
        self.game.save(update_fields=["status"])

    def test_opponent_hand_is_never_serialized_only_count(self):
        self.client.force_login(self.p2_user)
        response = self.client.get(reverse("api_game_state", args=[self.game.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        opponent_entries = [p for p in data["players"] if p["username"] == self.p1_user.username]
        self.assertEqual(len(opponent_entries), 1)
        self.assertNotIn("hand", opponent_entries[0])
        self.assertIn("hand_count", opponent_entries[0])
        self.assertEqual(opponent_entries[0]["hand_count"], 1)

    def test_my_own_hand_is_serialized(self):
        self.client.force_login(self.p1_user)
        response = self.client.get(reverse("api_game_state", args=[self.game.id]))
        data = response.json()
        mine = next(p for p in data["players"] if p["username"] == self.p1_user.username)
        self.assertIn("hand", mine)
        self.assertEqual(len(mine["hand"]), 1)


class CsrfEnforcedTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = make_users(1)[0]
        self.client.force_login(self.user)
        self.game = make_game(self.user)
        GameEngine(self.game).add_player(self.user)

    def test_play_without_csrf_token_is_rejected(self):
        response = self.client.post(
            reverse("api_play_card", args=[self.game.id]),
            data=json.dumps({"game_card_id": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
