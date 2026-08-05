import json
import re

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from game.tests.i18n import LanguageIsolationMixin
from islands.models import Shot
from islands.services import add_bot, create_game, fire, join_game, ready_player, start_bot_game

from .factories import deploy_all, make_catalog, make_users, ready_both


@override_settings(ROOT_URLCONF="islands.tests.urls")
class IslandApiTests(LanguageIsolationMixin, TestCase):
    def setUp(self):
        make_catalog()
        self.host, self.guest, self.outsider = make_users()
        self.game = create_game(self.host)
        self.game, _ = join_game(self.game.id, self.guest)

    def post_json(self, name, user, payload, **url_kwargs):
        self.client.force_login(user)
        return self.client.post(
            reverse(
                f"islands:{name}",
                kwargs={"game_id": self.game.id, **url_kwargs},
            ),
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
        self.assertTrue(response.json()["action_result"]["keeps_turn"])
        self.assertEqual(response.json()["action_result"]["combo"], 1)
        self.assertEqual(Shot.objects.count(), 1)

        host_miss = self.post_json(
            "api_fire",
            self.host,
            {"row": 6, "col": 7, "expected_turn_revision": response.json()["turn_revision"]},
        )
        self.assertFalse(host_miss.json()["action_result"]["keeps_turn"])
        self.assertEqual(host_miss.json()["action_result"]["combo"], 0)
        guest_miss = self.post_json(
            "api_fire",
            self.guest,
            {"row": 6, "col": 6, "expected_turn_revision": host_miss.json()["turn_revision"]},
        )
        duplicate = self.post_json(
            "api_fire",
            self.host,
            {"row": 0, "col": 0, "expected_turn_revision": guest_miss.json()["turn_revision"]},
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("déjà", duplicate.json()["error"])
        self.assertEqual(Shot.objects.count(), 3)

    def test_payload_validation_and_http_methods_are_strict(self):
        boolean_revision = self.post_json("api_ready", self.host, {"expected_turn_revision": True})
        invalid_json_url = reverse("islands:api_place", kwargs={"game_id": self.game.id})
        self.client.force_login(self.host)
        invalid_json = self.client.post(invalid_json_url, data="{", content_type="application/json")
        get_mutation = self.client.get(reverse("islands:api_fire", kwargs={"game_id": self.game.id}))

        self.assertEqual(boolean_revision.status_code, 400)
        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(get_mutation.status_code, 405)

    def test_api_validation_errors_follow_the_browser_language(self):
        self.client.force_login(self.host)
        url = reverse("islands:api_place", kwargs={"game_id": self.game.id})

        french = self.client.post(
            url,
            data="{",
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="fr",
        )
        english = self.client.post(
            url,
            data="{",
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(french.json()["error"], "Requête JSON invalide.")
        self.assertEqual(english.json()["error"], "Invalid JSON request.")

    def test_lobby_poll_lists_open_and_personal_games(self):
        self.client.force_login(self.host)
        response = self.client.get(reverse("islands:api_lobby_state"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["open_games"], [])
        self.assertIn(str(self.game.id), response.json()["my_game_ids"])
        self.assertEqual(response.json()["my_games"][0]["player_count"], 2)

    def test_host_adds_removes_and_starts_a_revision_protected_bot(self):
        self.game = create_game(self.host)
        added = self.post_json(
            "api_add_bot",
            self.host,
            {"expected_turn_revision": self.game.turn_revision},
        )

        self.assertEqual(added.status_code, 200)
        added_state = added.json()
        bot = next(player for player in added_state["players"] if player["is_bot"])
        self.assertTrue(added_state["can_start"])
        self.assertEqual(added_state["opponent_formations"], [])
        stale = self.post_json(
            "api_add_bot",
            self.host,
            {"expected_turn_revision": self.game.turn_revision},
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.game.players.filter(user__isnull=True).count(), 1)

        removed = self.post_json(
            "api_remove_bot",
            self.host,
            {"expected_turn_revision": added_state["turn_revision"]},
            bot_id=bot["id"],
        )
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.json()["can_add_bot"])

        added_again = self.post_json(
            "api_add_bot",
            self.host,
            {"expected_turn_revision": removed.json()["turn_revision"]},
        )
        started = self.post_json(
            "api_start",
            self.host,
            {"expected_turn_revision": added_again.json()["turn_revision"]},
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["status"], "PLACEMENT")
        self.assertEqual(started.json()["opponent_formations"], [])
        bot_model = self.game.players.get(user__isnull=True)
        self.assertTrue(bot_model.is_ready)
        self.assertTrue(all(formation.is_placed for formation in bot_model.formations.all()))

    def test_only_a_participant_host_can_manage_bots(self):
        self.client.force_login(self.guest)
        non_host = self.client.post(
            reverse("islands:api_add_bot", kwargs={"game_id": self.game.id}),
            data=json.dumps({"expected_turn_revision": self.game.turn_revision}),
            content_type="application/json",
        )
        self.assertEqual(non_host.status_code, 403)

        solo = create_game(self.host)
        self.game = solo
        outsider = self.post_json(
            "api_add_bot",
            self.outsider,
            {"expected_turn_revision": solo.turn_revision},
        )
        self.assertEqual(outsider.status_code, 403)
        self.assertFalse(solo.players.filter(user__isnull=True).exists())

    def test_revisioned_bot_turn_plays_once_and_keeps_the_board_private(self):
        self.game = create_game(self.host)
        self.game = add_bot(self.game.id, self.host, self.game.turn_revision)
        self.game = start_bot_game(self.game.id, self.host, self.game.turn_revision)
        self.game = deploy_all(self.game, self.host)
        self.game = ready_player(self.game.id, self.host, self.game.turn_revision)
        bot = self.game.players.get(user__isnull=True)
        target = bot.formations.first().cells[0]
        self.game, _ = fire(self.game.id, self.host, *target, self.game.turn_revision)
        occupied = {cell for formation in bot.formations.all() for cell in formation.cells}
        empty = next((row, col) for row in range(8) for col in range(8) if (row, col) not in occupied)
        self.game, _ = fire(self.game.id, self.host, *empty, self.game.turn_revision)
        bot_revision = self.game.turn_revision

        response = self.post_json(
            "api_bot_turn",
            self.host,
            {"expected_turn_revision": bot_revision},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Shot.objects.filter(shooter=bot).count(), 1)
        self.assertEqual(
            response.json()["bot_turn_pending"],
            response.json()["action_result"]["result"] != "MISS",
        )
        self.assertEqual(response.json()["opponent_formations"], [])
        repeated = self.post_json(
            "api_bot_turn",
            self.host,
            {"expected_turn_revision": bot_revision},
        )
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(Shot.objects.filter(shooter=bot).count(), 1)


@override_settings(ROOT_URLCONF="islands.tests.urls")
class IslandPageTests(LanguageIsolationMixin, TestCase):
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

    def test_lobby_has_complete_french_and_english_copy_and_seo(self):
        self.client.force_login(self.host)
        url = reverse("islands:lobby")

        french = self.client.get(url, HTTP_ACCEPT_LANGUAGE="fr")
        english = self.client.get(url, HTTP_ACCEPT_LANGUAGE="en")

        self.assertContains(french, "Bataille des Îles Pokémon en ligne — PokéTable")
        self.assertContains(french, "Créer un archipel")
        self.assertContains(french, "Grille 8 × 8")
        self.assertContains(french, "Pokémon marin 1")
        self.assertContains(english, "Pokémon Island Battle Online — PokéTable")
        self.assertContains(english, "Create an archipelago")
        self.assertContains(english, "8 × 8 grid")
        self.assertContains(english, "Sea Pokemon 1")
        self.assertContains(english, "Play Pokémon Island Battle free online")
        self.assertNotContains(english, "Créer un archipel")

    def test_participant_page_exposes_all_four_api_urls_and_accessible_grid(self):
        game = create_game(self.host)
        join_game(game.id, self.guest)
        self.client.force_login(self.host)
        response = self.client.get(reverse("islands:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "islands/detail.html")
        for name in (
            "api_state",
            "api_add_bot",
            "api_start",
            "api_place",
            "api_ready",
            "api_fire",
            "api_bot_turn",
        ):
            self.assertContains(response, reverse(f"islands:{name}", kwargs={"game_id": game.id}))
        self.assertContains(
            response,
            reverse("islands:api_remove_bot", kwargs={"game_id": game.id, "bot_id": 0}),
        )
        self.assertContains(response, 'role="grid"')
        self.assertContains(response, "Utilise les flèches")

    def test_detail_and_dynamic_state_follow_the_browser_language(self):
        game = create_game(self.host)
        join_game(game.id, self.guest)
        self.client.force_login(self.host)
        url = reverse("islands:game_detail", kwargs={"game_id": game.id})

        french = self.client.get(url, HTTP_ACCEPT_LANGUAGE="fr")
        english = self.client.get(url, HTTP_ACCEPT_LANGUAGE="en")

        self.assertContains(french, "Déploie ton escouade")
        self.assertEqual(french.context["game_state"]["ui"]["result_hit"], "Touché")
        self.assertContains(english, "Deploy your squad")
        self.assertContains(english, "Use the arrow keys to move")
        self.assertContains(english, "Private game map for a Pokémon Island Battle match")
        self.assertNotContains(english, "Déploie ton escouade")
        state = english.context["game_state"]
        self.assertEqual(state["ui"]["result_hit"], "Hit")
        self.assertEqual(state["ui"]["your_turn"], "Your turn to explore")
        self.assertTrue(state["own_formations"][0]["pokemon"]["name"].startswith("Sea Pokemon"))

    def test_waiting_page_offers_responsive_ai_controls_to_the_host(self):
        game = create_game(self.host)
        self.client.force_login(self.host)
        response = self.client.get(reverse("islands:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ajouter une IA")
        self.assertContains(response, "data-waiting-players")
        self.assertContains(response, reverse("islands:api_add_bot", kwargs={"game_id": game.id}))
        self.assertContains(response, reverse("islands:api_start", kwargs={"game_id": game.id}))

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


class IslandJavascriptRegressionTests(SimpleTestCase):
    def test_i18n_copy_helper_is_not_shadowed_by_dom_nodes(self):
        source = (settings.BASE_DIR / "islands" / "static" / "islands" / "js" / "game.js").read_text()

        self.assertIn('const copy = (key, fallback = "")', source)
        self.assertEqual(re.findall(r"\b(?:const|let|var)\s+copy\b", source), ["const copy"])
