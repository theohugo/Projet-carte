import json
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from game.game_engine import GameEngine
from game.models import Game, GameCard
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

    def test_lobby_state_lists_waiting_games_for_live_refresh(self):
        game = make_game(self.user)
        GameEngine(game).add_player(self.user)

        response = self.client.get(reverse("api_lobby_state"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["open_game_ids"], [str(game.id)])


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


class ApiStartGameTests(TestCase):
    """La salle d'attente (nombre de joueurs, bouton Démarrer) est pilotée par
    le polling de /state/ + cet endpoint JSON, pas par un rendu Django statique
    — sinon les autres joueurs déjà sur la page ne voient jamais la partie
    démarrer sans rafraîchir manuellement."""

    def setUp(self):
        make_cards(make_types())
        self.owner, self.other = make_users(2)
        self.game = make_game(self.owner)
        engine = GameEngine(self.game)
        engine.add_player(self.owner)
        engine.add_player(self.other)

    def test_non_creator_cannot_start_via_api(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("api_start_game", args=[self.game.id]))
        self.assertEqual(response.status_code, 403)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.EN_ATTENTE)

    @mock.patch("game.game_engine.HAND_SIZE", 2)
    def test_creator_can_start_via_api(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("api_start_game", args=[self.game.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "EN_COURS")
        self.assertTrue(data["is_creator"])
        self.assertEqual(data["max_players"], self.game.max_players)

    @mock.patch("game.game_engine.HAND_SIZE", 2)
    def test_api_start_cannot_be_repeated(self):
        self.client.force_login(self.owner)
        url = reverse("api_start_game", args=[self.game.id])
        self.assertEqual(self.client.post(url).status_code, 200)
        card_count = GameCard.objects.filter(game=self.game).count()

        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(GameCard.objects.filter(game=self.game).count(), card_count)

    def test_state_reflects_new_player_without_refresh(self):
        """Le joueur fondateur, déjà en train de poller /state/, doit voir le
        nouveau joueur apparaître au poll suivant (pas besoin de F5) — passe
        par le vrai flux HTTP (join_game) pour vérifier l'invalidation du
        cache, pas un appel direct au moteur qui la contournerait."""
        third = make_users(1)[0]
        self.client.force_login(self.owner)
        before = self.client.get(reverse("api_game_state", args=[self.game.id])).json()
        self.assertEqual(len(before["players"]), 2)

        joiner_client = Client()
        joiner_client.force_login(third)
        joiner_client.post(reverse("join_game", args=[self.game.id]))

        after = self.client.get(reverse("api_game_state", args=[self.game.id])).json()
        self.assertEqual(len(after["players"]), 3)


class GameBoardRenderingTests(TestCase):
    @mock.patch("game.game_engine.HAND_SIZE", 2)
    def test_own_hand_renders_disabled_cards_with_type_icons(self):
        types = make_types()
        make_cards(types)
        first, second = make_users(2)
        game = make_game(first)
        engine = GameEngine(game)
        engine.add_player(first)
        engine.add_player(second)
        engine.start_game()

        self.client.force_login(second)
        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="type-energy-icon"')
        self.assertContains(response, "Non jouable")

    @mock.patch("game.game_engine.HAND_SIZE", 3)
    def test_opponent_hand_renders_exact_count_as_card_backs(self):
        types = make_types()
        make_cards(types)
        first, second = make_users(2)
        game = make_game(first)
        engine = GameEngine(game)
        engine.add_player(first)
        second_player = engine.add_player(second)
        engine.start_game()

        self.client.force_login(first)
        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-player-id="{second_player.id}"')
        self.assertContains(response, second.username)
        self.assertContains(response, 'class="opponent-card-back"', count=3)
        self.assertEqual(len(response.context["opponents"][0]["card_back_slots"]), 3)
        self.assertContains(response, "data-motion-deck")
        self.assertContains(response, "data-motion-discard")

    def test_large_opponent_hand_is_capped_without_leaking_into_json(self):
        types = make_types()
        cards = make_cards(types)
        first, second = make_users(2)
        game = make_game(first)
        engine = GameEngine(game)
        engine.add_player(first)
        second_player = engine.add_player(second)
        for order_index in range(12):
            GameCard.objects.create(
                game=game,
                pokemon_card=cards["charmander"],
                location=GameCard.Location.MAIN,
                owner=second_player,
                order_index=order_index,
            )
        game.status = Game.Status.EN_COURS
        game.save(update_fields=["status"])

        self.client.force_login(first)
        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertEqual(response.status_code, 200)
        opponent = response.context["opponents"][0]
        self.assertEqual(len(opponent["card_back_slots"]), 10)
        self.assertEqual(opponent["hidden_card_count"], 2)
        self.assertContains(response, 'class="opponent-card-back"', count=10)
        self.assertContains(response, 'class="opponent-card-overflow" aria-hidden="true">+2</span>')
        self.assertNotContains(response, '"card_back_slots"')
        self.assertNotContains(response, '"hidden_card_count"')


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
        opponent = opponent_entries[0]
        self.assertEqual(
            set(opponent),
            {
                "id",
                "username",
                "turn_order",
                "score",
                "has_protection",
                "is_current_turn",
                "hand_count",
            },
        )
        self.assertEqual(opponent["hand_count"], 1)

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
