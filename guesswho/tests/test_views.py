import json

from django.test import TestCase, override_settings
from django.urls import reverse

from game.tests.i18n import LanguageIsolationMixin
from guesswho.models import GuessWhoTurn
from guesswho.services import choose_target, create_game, join_game

from .factories import make_catalog, make_users


@override_settings(ROOT_URLCONF="guesswho.tests.urls")
class GuessWhoApiTests(LanguageIsolationMixin, TestCase):
    def setUp(self):
        self.cards = make_catalog()
        self.host, self.guest, self.outsider = make_users()
        self.game = create_game(self.host)
        self.game, _ = join_game(self.game.id, self.guest)
        self.game = choose_target(
            self.game.id,
            self.host,
            self.cards[0].id,
            self.game.turn_revision,
        )
        self.game = choose_target(
            self.game.id,
            self.guest,
            self.cards[1].id,
            self.game.turn_revision,
        )

    def post_json(self, name, user, payload, **kwargs):
        self.client.force_login(user)
        return self.client.post(
            reverse(f"guesswho:{name}", kwargs={"game_id": self.game.id, **kwargs}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_state_requires_authentication_and_participation(self):
        state_url = reverse("guesswho:api_state", kwargs={"game_id": self.game.id})
        response = self.client.get(state_url)
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.outsider)
        response = self.client.get(state_url)
        self.assertEqual(response.status_code, 403)

    def test_accept_language_adds_a_localized_roster_name(self):
        self.client.force_login(self.host)
        url = reverse("guesswho:api_state", kwargs={"game_id": self.game.id})

        french = self.client.get(url, HTTP_ACCEPT_LANGUAGE="fr-FR").json()
        english = self.client.get(url, HTTP_ACCEPT_LANGUAGE="en-GB").json()

        self.assertEqual(french["language"], "fr")
        self.assertEqual(french["roster"][0]["name"], french["roster"][0]["name_fr"])
        self.assertEqual(english["language"], "en")
        self.assertEqual(english["roster"][0]["name"], english["roster"][0]["name_en"])
        self.assertIn("name_fr", english["roster"][0])

    def test_lobby_state_is_public_but_only_lists_my_game_after_login(self):
        lobby_state_url = reverse("guesswho:api_lobby_state")
        anonymous = self.client.get(lobby_state_url)

        self.assertEqual(anonymous.status_code, 200)
        self.assertEqual(anonymous.json()["my_games"], [])
        self.assertEqual(anonymous.json()["my_game_ids"], [])

        self.client.force_login(self.host)
        response = self.client.get(lobby_state_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["open_games"], [])
        self.assertIn(str(self.game.id), response.json()["my_game_ids"])
        self.assertEqual(response.json()["my_games"][0]["status"], "EN_COURS")
        self.assertEqual(response.json()["my_games"][0]["player_count"], 2)

    def test_question_and_answer_endpoints_return_updated_state(self):
        response = self.post_json(
            "api_ask_question",
            self.host,
            {
                "question": "Est-il de type Incolore ?",
                "expected_turn_revision": self.game.turn_revision,
            },
        )
        self.assertEqual(response.status_code, 200)
        asked_state = response.json()
        self.assertEqual(asked_state["pending_question"]["question"], "Est-il de type Incolore ?")
        self.assertFalse(asked_state["is_my_turn"])

        response = self.post_json(
            "api_answer_question",
            self.guest,
            {
                "answer": True,
                "expected_turn_revision": asked_state["turn_revision"],
            },
        )
        self.assertEqual(response.status_code, 200)
        answered_state = response.json()
        self.assertIsNone(answered_state["pending_question"])
        self.assertTrue(answered_state["is_my_turn"])
        self.assertEqual(answered_state["history"][0]["answer"], True)

    def test_duplicate_request_returns_stale_state_without_duplicate_turn(self):
        payload = {
            "question": "Possède-t-il une évolution ?",
            "expected_turn_revision": self.game.turn_revision,
        }
        first = self.post_json("api_ask_question", self.host, payload)
        second = self.post_json("api_ask_question", self.host, payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "stale_revision")
        self.assertEqual(second.json()["state"]["turn_revision"], first.json()["turn_revision"])
        self.assertEqual(GuessWhoTurn.objects.count(), 1)

    def test_toggle_endpoint_changes_only_callers_private_board(self):
        response = self.post_json(
            "api_toggle_candidate",
            self.host,
            {
                "is_eliminated": True,
                "expected_turn_revision": self.game.turn_revision,
            },
            pokemon_card_id=self.cards[4].id,
        )
        self.assertEqual(response.status_code, 200)
        host_card = next(card for card in response.json()["roster"] if card["id"] == self.cards[4].id)
        self.assertTrue(host_card["is_eliminated"])

        self.client.force_login(self.guest)
        guest_state = self.client.get(reverse("guesswho:api_state", kwargs={"game_id": self.game.id})).json()
        guest_card = next(card for card in guest_state["roster"] if card["id"] == self.cards[4].id)
        self.assertFalse(guest_card["is_eliminated"])

    def test_reset_endpoint_reactivates_all_callers_candidates_only(self):
        for user, card in (
            (self.host, self.cards[4]),
            (self.host, self.cards[5]),
            (self.guest, self.cards[6]),
        ):
            response = self.post_json(
                "api_toggle_candidate",
                user,
                {
                    "is_eliminated": True,
                    "expected_turn_revision": self.game.turn_revision,
                },
                pokemon_card_id=card.id,
            )
            self.assertEqual(response.status_code, 200)

        response = self.post_json(
            "api_reset_candidates",
            self.host,
            {"expected_turn_revision": self.game.turn_revision},
        )

        self.assertEqual(response.status_code, 200)
        eliminated_ids = {card["id"] for card in response.json()["roster"] if card["is_eliminated"]}
        self.assertEqual(eliminated_ids, set())
        self.client.force_login(self.guest)
        guest_state = self.client.get(reverse("guesswho:api_state", kwargs={"game_id": self.game.id})).json()
        guest_card = next(card for card in guest_state["roster"] if card["id"] == self.cards[6].id)
        self.assertTrue(guest_card["is_eliminated"])

    def test_reset_endpoint_returns_stale_state_and_refuses_finished_game(self):
        stale = self.post_json(
            "api_reset_candidates",
            self.host,
            {"expected_turn_revision": self.game.turn_revision - 1},
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "stale_revision")

        finished = self.post_json(
            "api_guess",
            self.host,
            {
                "pokemon_card_id": self.cards[1].id,
                "expected_turn_revision": self.game.turn_revision,
            },
        ).json()
        reset = self.post_json(
            "api_reset_candidates",
            self.host,
            {"expected_turn_revision": finished["turn_revision"]},
        )
        self.assertEqual(reset.status_code, 400)
        self.assertIn("terminée", reset.json()["error"])

    def test_guess_endpoint_ends_game_on_wrong_guess(self):
        response = self.post_json(
            "api_guess",
            self.host,
            {
                "pokemon_card_id": self.cards[3].id,
                "expected_turn_revision": self.game.turn_revision,
            },
        )

        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertEqual(state["status"], "TERMINEE")
        self.assertEqual(state["winner"]["username"], self.guest.username)
        self.assertTrue(all(player["target"] is not None for player in state["players"]))

    def test_payload_validation_is_strict(self):
        answer = self.post_json(
            "api_answer_question",
            self.guest,
            {"answer": "oui", "expected_turn_revision": self.game.turn_revision},
        )
        revision = self.post_json(
            "api_ask_question",
            self.host,
            {"question": "Test ?", "expected_turn_revision": True},
        )
        invalid_json_url = reverse("guesswho:api_ask_question", kwargs={"game_id": self.game.id})
        self.client.force_login(self.host)
        invalid_json = self.client.post(
            invalid_json_url,
            data="{",
            content_type="application/json",
        )

        self.assertEqual(answer.status_code, 400)
        self.assertEqual(revision.status_code, 400)
        self.assertEqual(invalid_json.status_code, 400)

    def test_accept_language_localizes_invalid_json_and_business_errors(self):
        url = reverse("guesswho:api_ask_question", kwargs={"game_id": self.game.id})
        self.client.force_login(self.guest)

        invalid_json = self.client.post(
            url,
            data="{",
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="en-US",
        )
        out_of_turn = self.client.post(
            url,
            data=json.dumps(
                {
                    "question": "Is it a Water type?",
                    "expected_turn_revision": self.game.turn_revision,
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="en-US",
        )

        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(invalid_json.json()["error"], "Invalid JSON request.")
        self.assertEqual(out_of_turn.status_code, 400)
        self.assertEqual(out_of_turn.json()["error"], "It is not your turn.")

    def test_mutating_endpoints_refuse_get(self):
        self.client.force_login(self.host)
        url = reverse("guesswho:api_guess", kwargs={"game_id": self.game.id})
        self.assertEqual(self.client.get(url).status_code, 405)


class GuessWhoIntegratedPageTests(LanguageIsolationMixin, TestCase):
    def setUp(self):
        make_catalog()
        self.host, self.guest, self.outsider = make_users()

    def test_lobby_renders_inside_poketable_with_live_state_endpoint(self):
        self.client.force_login(self.host)

        response = self.client.get(reverse("guesswho:lobby"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "guesswho/lobby.html")
        self.assertContains(response, "PokéTable")
        self.assertContains(response, reverse("guesswho:api_lobby_state"))
        self.assertContains(response, reverse("home"))

    def test_anonymous_visitors_can_read_the_lobby_and_public_state(self):
        game = create_game(self.host)

        page = self.client.get(reverse("guesswho:lobby"))
        state = self.client.get(reverse("guesswho:api_lobby_state"))

        self.assertEqual(page.status_code, 200)
        self.assertTemplateUsed(page, "guesswho/lobby.html")
        self.assertNotContains(page, "guest_gate")
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()["my_games"], [])
        self.assertEqual(state.json()["my_game_ids"], [])
        self.assertIn(str(game.id), [entry["id"] for entry in state.json()["open_games"]])
        self.assertContains(page, f'action="{reverse("guesswho:create_game")}"', html=False)
        self.assertContains(
            page,
            f'action="{reverse("guesswho:join_game", kwargs={"game_id": game.id})}"',
            html=False,
        )

        joined = self.client.post(reverse("guesswho:join_game", kwargs={"game_id": game.id}))
        self.assertRedirects(joined, reverse("guesswho:game_detail", kwargs={"game_id": game.id}))
        self.assertTrue(game.players.filter(user__profile__is_guest=True).exists())

    def test_accept_language_renders_the_lobby_in_english(self):
        self.client.force_login(self.host)

        response = self.client.get(reverse("guesswho:lobby"), HTTP_ACCEPT_LANGUAGE="en-GB")

        self.assertContains(response, "Create a table")
        self.assertContains(response, "How to play")
        self.assertNotContains(response, "Créer une table")

    def test_joined_player_can_render_the_complete_board_contract(self):
        game = create_game(self.host)
        join_game(game.id, self.guest)
        self.client.force_login(self.host)

        response = self.client.get(reverse("guesswho:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "guesswho/detail.html")
        self.assertContains(response, "guesswho-game")
        self.assertContains(response, reverse("guesswho:api_state", kwargs={"game_id": game.id}))
        self.assertContains(
            response,
            reverse("guesswho:api_reset_candidates", kwargs={"game_id": game.id}),
        )
        self.assertContains(response, 'maxlength="500"')

    def test_non_participant_can_accept_an_open_table_invitation(self):
        game = create_game(self.host)
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("guesswho:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "join_invitation.html")
        self.assertContains(
            response,
            reverse("guesswho:join_game", kwargs={"game_id": game.id}),
        )

        response = self.client.post(reverse("guesswho:join_game", kwargs={"game_id": game.id}))
        self.assertRedirects(
            response,
            reverse("guesswho:game_detail", kwargs={"game_id": game.id}),
        )
        self.assertTrue(game.players.filter(user=self.outsider).exists())

    def test_non_participant_cannot_view_a_closed_table(self):
        game = create_game(self.host)
        join_game(game.id, self.guest)
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("guesswho:game_detail", kwargs={"game_id": game.id}))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "join_invitation.html")
        self.assertContains(response, "Invitation expirée", status_code=403)
