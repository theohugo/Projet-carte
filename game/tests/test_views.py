import json
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from game.game_engine import GameEngine
from game.models import Game, GameCard
from game.tcg_types import TCG_TYPES
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


class SignupRedirectTests(TestCase):
    def test_new_account_returns_to_a_safe_game_invitation(self):
        (owner,) = make_users(1)
        game = make_game(owner)
        GameEngine(game).add_player(owner)
        invitation_path = reverse("game_detail", args=[game.id])

        response = self.client.get(invitation_path)
        login_response = self.client.get(response.url)

        self.assertContains(login_response, f"?next={invitation_path}")
        response = self.client.post(
            reverse("signup"),
            {
                "username": "invitee",
                "password1": "A-very-safe-password-2026!",
                "password2": "A-very-safe-password-2026!",
                "next": invitation_path,
            },
        )
        self.assertRedirects(response, invitation_path, fetch_redirect_response=False)
        self.assertEqual(self.client.get(invitation_path).status_code, 200)

    def test_signup_rejects_an_external_next_url(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "safe-user",
                "password1": "A-very-safe-password-2026!",
                "password2": "A-very-safe-password-2026!",
                "next": "https://attacker.example/steal",
            },
        )

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)


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
        self.assertEqual(
            response.json()["open_games"],
            [
                {
                    "id": str(game.id),
                    "player_count": 1,
                    "max_players": game.max_players,
                }
            ],
        )


class PermissionTests(TestCase):
    def setUp(self):
        self.owner, self.outsider = make_users(2)
        self.game = make_game(self.owner)
        GameEngine(self.game).add_player(self.owner)

    def test_non_participant_can_accept_an_invitation_to_an_open_game(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("game_detail", args=[self.game.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "join_invitation.html")
        self.assertContains(response, reverse("join_game", args=[self.game.id]))

        response = self.client.post(reverse("join_game", args=[self.game.id]))
        self.assertRedirects(response, reverse("game_detail", args=[self.game.id]))
        self.assertTrue(self.game.players.filter(user=self.outsider).exists())

    def test_non_participant_cannot_view_a_started_game(self):
        self.game.status = Game.Status.EN_COURS
        self.game.save(update_fields=["status"])
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("game_detail", args=[self.game.id]))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "join_invitation.html")
        self.assertContains(response, "Invitation expirée", status_code=403)

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
        with self.captureOnCommitCallbacks(execute=True):
            response = joiner_client.post(reverse("join_game", args=[self.game.id]))
        self.assertEqual(response.status_code, 302)

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
        self.assertContains(response, 'class="tcg-energy-icon"')
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

    def test_tcg_type_selector_and_wild_card_contract_are_rendered(self):
        types = make_types()
        cards = make_cards(types)
        first, second = make_users(2)
        game = make_game(first)
        engine = GameEngine(game)
        first_player = engine.add_player(first)
        engine.add_player(second)
        GameCard.objects.create(
            game=game,
            pokemon_card=cards["zapdos"],
            location=GameCard.Location.MAIN,
            owner=first_player,
            order_index=0,
        )
        game.status = Game.Status.EN_COURS
        game.save(update_fields=["status"])

        self.client.force_login(first)
        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["declared_tcg_types"], TCG_TYPES)
        self.assertContains(
            response,
            'data-requires-tcg-type-choice="true"',
            count=1,
        )
        self.assertContains(
            response,
            "data-declared-tcg-type=",
            count=len(TCG_TYPES),
        )


class BotLobbyViewTests(TestCase):
    def setUp(self):
        self.owner, self.other = make_users(2)
        self.game = make_game(self.owner)
        self.engine = GameEngine(self.game)
        self.engine.add_player(self.owner)
        self.engine.add_player(self.other)

    def test_creator_can_add_render_and_remove_bot(self):
        self.client.force_login(self.owner)

        with self.captureOnCommitCallbacks(execute=True):
            add_response = self.client.post(reverse("add_bot", args=[self.game.id]))

        self.assertRedirects(add_response, reverse("game_detail", args=[self.game.id]))
        bot = self.game.players.get(user__isnull=True)

        detail_response = self.client.get(reverse("game_detail", args=[self.game.id]))
        self.assertContains(detail_response, bot.display_name)
        self.assertContains(detail_response, "Joueur IA")
        self.assertContains(detail_response, reverse("add_bot", args=[self.game.id]))
        self.assertContains(
            detail_response,
            reverse("remove_bot", args=[self.game.id, bot.id]),
        )

        with self.captureOnCommitCallbacks(execute=True):
            remove_response = self.client.post(reverse("remove_bot", args=[self.game.id, bot.id]))

        self.assertRedirects(remove_response, reverse("game_detail", args=[self.game.id]))
        self.assertFalse(self.game.players.filter(user__isnull=True).exists())

    def test_non_creator_cannot_see_or_use_bot_controls(self):
        bot = self.engine.add_bot()
        add_url = reverse("add_bot", args=[self.game.id])
        remove_url = reverse("remove_bot", args=[self.game.id, bot.id])
        self.client.force_login(self.other)

        detail_response = self.client.get(reverse("game_detail", args=[self.game.id]))
        self.assertNotContains(detail_response, add_url)
        self.assertNotContains(detail_response, remove_url)
        self.assertEqual(self.client.post(add_url).status_code, 403)
        self.assertEqual(self.client.post(remove_url).status_code, 403)
        self.assertTrue(self.game.players.filter(pk=bot.id, user__isnull=True).exists())

    def test_state_identifies_bot_without_exposing_a_hand(self):
        bot = self.engine.add_bot()
        self.client.force_login(self.owner)

        response = self.client.get(reverse("api_game_state", args=[self.game.id]))

        self.assertEqual(response.status_code, 200)
        bot_state = next(player for player in response.json()["players"] if player["id"] == bot.id)
        self.assertIs(bot_state["is_bot"], True)
        self.assertEqual(bot_state["username"], bot.display_name)
        self.assertNotIn("hand", bot_state)
        self.assertEqual(bot_state["hand_count"], 0)


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

        first_p1_card = GameCard.objects.filter(
            game=self.game,
            location=GameCard.Location.PIOCHE,
            pokemon_card=self.cards["zapdos"],
        ).first()
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
                "is_bot",
                "turn_order",
                "score",
                "has_protection",
                "is_current_turn",
                "hand_count",
            },
        )
        self.assertEqual(opponent["hand_count"], 1)
        self.assertIs(opponent["is_bot"], False)

    def test_my_own_hand_is_serialized(self):
        self.client.force_login(self.p1_user)
        response = self.client.get(reverse("api_game_state", args=[self.game.id]))
        data = response.json()
        mine = next(p for p in data["players"] if p["username"] == self.p1_user.username)
        self.assertIn("hand", mine)
        self.assertEqual(len(mine["hand"]), 1)

    def test_state_uses_tcg_type_contract_and_marks_wild_cards(self):
        active_tcg_type = next(tcg_type for tcg_type in TCG_TYPES if tcg_type.slug == "lightning")
        self.game.active_tcg_type = active_tcg_type.slug
        self.game.save(update_fields=["active_tcg_type"])
        self.client.force_login(self.p1_user)

        response = self.client.get(reverse("api_game_state", args=[self.game.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["active_tcg_type"], active_tcg_type.as_dict())
        self.assertEqual(
            data["available_tcg_types"],
            [tcg_type.as_dict() for tcg_type in TCG_TYPES],
        )
        self.assertNotIn("active_type", data)
        mine = next(player for player in data["players"] if player["id"] == self.gp1.id)
        card = mine["hand"][0]
        self.assertEqual(
            set(card),
            {
                "id",
                "pokedex_id",
                "name_fr",
                "name_en",
                "sprite_url",
                "tcg_type",
                "tcg_type_label",
                "is_legendary",
                "requires_tcg_type_choice",
                "action",
                "action_label",
            },
        )
        self.assertEqual(card["tcg_type"], "lightning")
        self.assertEqual(card["tcg_type_label"], "Électrique")
        self.assertIs(card["requires_tcg_type_choice"], True)


class PlayCardPayloadValidationTests(TestCase):
    def setUp(self):
        (self.user,) = make_users(1)
        self.game = make_game(self.user)
        GameEngine(self.game).add_player(self.user)
        self.client.force_login(self.user)
        self.url = reverse("api_play_card", args=[self.game.id])

    def post_payload(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_json_payload_must_be_an_object(self):
        response = self.post_payload([])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "La requête doit être un objet JSON.")

    def test_declared_tcg_type_must_be_a_string_or_null(self):
        response = self.post_payload({"game_card_id": 1, "declared_tcg_type": {}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Type JCC déclaré invalide.")

    def test_game_card_id_must_be_a_positive_integer(self):
        for invalid_id in ("abc", {}, [], True, 0, -1):
            with self.subTest(invalid_id=invalid_id):
                response = self.post_payload({"game_card_id": invalid_id})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "Identifiant de carte invalide.")

    def test_invalid_utf8_payload_is_rejected(self):
        response = self.client.post(
            self.url,
            data=b"\xff",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Requête invalide.")


class BotTurnApiViewTests(TestCase):
    def setUp(self):
        self.owner, self.other, self.outsider = make_users(3)
        self.game = make_game(self.owner)
        engine = GameEngine(self.game)
        engine.add_player(self.owner)
        engine.add_player(self.other)
        self.game.status = Game.Status.EN_COURS
        self.game.turn_revision = 7
        self.game.save(update_fields=["status", "turn_revision"])
        self.url = reverse("api_bot_turn", args=[self.game.id])

    def post_turn(self, client, payload):
        return client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_non_participant_cannot_trigger_bot_turn(self):
        self.client.force_login(self.outsider)

        response = self.post_turn(self.client, {"expected_turn_revision": 7})

        self.assertEqual(response.status_code, 403)

    def test_invalid_turn_revision_is_rejected(self):
        self.client.force_login(self.owner)

        for payload in ({}, [], {"expected_turn_revision": True}, {"expected_turn_revision": "7"}):
            with self.subTest(payload=payload):
                response = self.post_turn(self.client, payload)
                self.assertEqual(response.status_code, 400)

    @mock.patch("game.api.perform_bot_turn")
    def test_human_current_turn_is_a_noop(self, perform_bot_turn):
        self.client.force_login(self.owner)

        response = self.post_turn(self.client, {"expected_turn_revision": 7})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["turn_revision"], 7)
        self.assertTrue(response.json()["is_my_turn"])
        perform_bot_turn.assert_not_called()


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
