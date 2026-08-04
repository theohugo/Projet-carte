import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from guesswho.models import GuessWhoCandidateState, GuessWhoGame, GuessWhoTurn
from guesswho.services import (
    ROSTER_SIZE,
    GuessWhoPermissionError,
    GuessWhoRosterError,
    GuessWhoStateError,
    StaleRevisionError,
    answer_question,
    ask_question,
    choose_target,
    create_game,
    guess_pokemon,
    join_game,
    reset_candidates,
    serialize_game_state,
    toggle_candidate,
)

from .factories import make_catalog, make_users


class GuessWhoServiceTests(TestCase):
    def setUp(self):
        self.cards = make_catalog()
        self.host, self.guest, self.outsider = make_users()

    def make_joined_game(self):
        game = create_game(self.host)
        game, _ = join_game(game.id, self.guest)
        return game

    def make_started_game(self):
        game = self.make_joined_game()
        game = choose_target(game.id, self.host, self.cards[0].id, game.turn_revision)
        game = choose_target(game.id, self.guest, self.cards[1].id, game.turn_revision)
        return game

    def test_creation_draws_a_random_roster_registers_host(self):
        game = create_game(self.host)

        self.assertEqual(game.status, GuessWhoGame.Status.EN_ATTENTE)
        self.assertEqual(game.turn_revision, 0)
        self.assertEqual(game.players.get().user, self.host)
        self.assertEqual(game.players.get().turn_order, 0)
        self.assertEqual(game.roster_cards.count(), 24)
        roster_ids = set(game.roster_cards.values_list("pokemon_card_id", flat=True))
        self.assertTrue(roster_ids.issubset({card.id for card in self.cards}))

    def test_creation_does_not_always_draw_the_same_roster(self):
        # Un vivier plus large que ROSTER_SIZE : sinon le tirage renvoie
        # toujours le catalogue entier et ne peut jamais varier.
        make_catalog(count=6, start=1000)

        rosters = set()
        for _ in range(20):
            game = create_game(self.host)
            rosters.add(frozenset(game.roster_cards.values_list("pokemon_card_id", flat=True)))
            game.delete()

        self.assertGreater(len(rosters), 1)

    def test_creation_is_rolled_back_when_catalog_is_too_small(self):
        self.cards[-2].delete()
        self.cards[-1].delete()

        with self.assertRaisesMessage(GuessWhoRosterError, "au moins 24 Pokémon"):
            create_game(self.host)

        self.assertFalse(GuessWhoGame.objects.exists())

    def test_only_one_guest_can_join_and_repeat_join_is_idempotent(self):
        game = create_game(self.host)
        game, guest_player = join_game(game.id, self.guest)
        repeated_game, repeated_player = join_game(game.id, self.guest)

        self.assertEqual(game.status, GuessWhoGame.Status.CHOIX)
        self.assertEqual(game.turn_revision, 1)
        self.assertEqual(repeated_game.turn_revision, 1)
        self.assertEqual(repeated_player.id, guest_player.id)
        self.assertEqual(game.players.count(), 2)
        with self.assertRaisesMessage(GuessWhoStateError, "n'accepte plus"):
            join_game(game.id, self.outsider)

    def test_two_secret_choices_start_the_game_with_host_turn(self):
        game = self.make_joined_game()

        game = choose_target(game.id, self.host, self.cards[0].id, game.turn_revision)
        self.assertEqual(game.status, GuessWhoGame.Status.CHOIX)
        game = choose_target(game.id, self.guest, self.cards[1].id, game.turn_revision)

        self.assertEqual(game.status, GuessWhoGame.Status.EN_COURS)
        self.assertEqual(game.current_turn.user, self.host)
        self.assertIsNotNone(game.started_at)
        self.assertEqual(game.turn_revision, 3)

    def test_target_must_belong_to_frozen_roster(self):
        game = self.make_joined_game()
        # Créée après coup : ne peut jamais figurer dans le plateau, déjà figé.
        outsider_card = make_catalog(count=1, start=1000)[0]

        with self.assertRaisesMessage(GuessWhoRosterError, "ne fait pas partie"):
            choose_target(game.id, self.host, outsider_card.id, game.turn_revision)

    def test_secret_target_is_locked_after_the_first_choice(self):
        game = self.make_joined_game()
        game = choose_target(game.id, self.host, self.cards[0].id, game.turn_revision)

        with self.assertRaisesMessage(GuessWhoStateError, "déjà verrouillé"):
            choose_target(game.id, self.host, self.cards[2].id, game.turn_revision)

        state = serialize_game_state(game, self.host)
        self.assertFalse(state["can_choose_target"])
        self.assertEqual(state["me"]["target"]["id"], self.cards[0].id)

    def test_question_answer_cycle_transfers_turn_to_responder(self):
        game = self.make_started_game()
        game = ask_question(game.id, self.host, "  Est-il   de type feu ?  ", game.turn_revision)

        pending = GuessWhoTurn.objects.get()
        self.assertEqual(pending.question, "Est-il de type feu ?")
        self.assertEqual(game.current_turn.user, self.host)
        self.assertFalse(serialize_game_state(game, self.host)["is_my_turn"])
        self.assertTrue(serialize_game_state(game, self.guest)["can_answer"])

        with self.assertRaises(GuessWhoPermissionError):
            answer_question(game.id, self.host, True, game.turn_revision)

        game = answer_question(game.id, self.guest, False, game.turn_revision)
        pending.refresh_from_db()
        self.assertIs(pending.answer, False)
        self.assertEqual(pending.responder.user, self.guest)
        self.assertEqual(game.current_turn.user, self.guest)
        self.assertTrue(serialize_game_state(game, self.guest)["is_my_turn"])

    def test_empty_or_oversized_questions_are_rejected(self):
        game = self.make_started_game()
        with self.assertRaisesMessage(GuessWhoStateError, "ne peut pas être vide"):
            ask_question(game.id, self.host, "  \n ", game.turn_revision)
        with self.assertRaisesMessage(GuessWhoStateError, "500 caractères"):
            ask_question(game.id, self.host, "x" * 501, game.turn_revision)

    def test_pending_question_blocks_another_action(self):
        game = self.make_started_game()
        game = ask_question(game.id, self.host, "Est-il légendaire ?", game.turn_revision)

        with self.assertRaisesMessage(GuessWhoStateError, "attend encore"):
            ask_question(game.id, self.host, "Vole-t-il ?", game.turn_revision)
        with self.assertRaisesMessage(GuessWhoStateError, "doit d'abord"):
            guess_pokemon(game.id, self.host, self.cards[1].id, game.turn_revision)

    def test_correct_guess_wins_and_reveals_both_targets(self):
        game = self.make_started_game()
        game = guess_pokemon(game.id, self.host, self.cards[1].id, game.turn_revision)

        self.assertEqual(game.status, GuessWhoGame.Status.TERMINEE)
        self.assertEqual(game.winner.user, self.host)
        self.assertIsNone(game.current_turn)
        state = serialize_game_state(game, self.host)
        self.assertTrue(all(player["target"] is not None for player in state["players"]))
        self.assertEqual(state["history"][-1]["guessed_card"]["id"], self.cards[1].id)
        self.assertIs(state["history"][-1]["is_correct"], True)

    def test_incorrect_guess_gives_victory_to_opponent(self):
        game = self.make_started_game()
        game = guess_pokemon(game.id, self.host, self.cards[2].id, game.turn_revision)

        self.assertEqual(game.winner.user, self.guest)
        self.assertIs(GuessWhoTurn.objects.get(kind=GuessWhoTurn.Kind.GUESS).is_correct, False)

    def test_candidate_state_is_reversible_and_private(self):
        game = self.make_started_game()
        turn_revision = game.turn_revision
        game = toggle_candidate(game.id, self.host, self.cards[5].id, True, game.turn_revision)

        host_state = serialize_game_state(game, self.host)
        guest_state = serialize_game_state(game, self.guest)
        host_card = next(card for card in host_state["roster"] if card["id"] == self.cards[5].id)
        guest_card = next(card for card in guest_state["roster"] if card["id"] == self.cards[5].id)
        self.assertTrue(host_card["is_eliminated"])
        self.assertFalse(guest_card["is_eliminated"])
        self.assertEqual(game.turn_revision, turn_revision)

        game = toggle_candidate(game.id, self.host, self.cards[5].id, False, game.turn_revision)
        self.assertFalse(GuessWhoCandidateState.objects.get().is_eliminated)

    def test_reset_candidates_is_bulk_private_and_does_not_advance_revision(self):
        game = self.make_started_game()
        original_revision = game.turn_revision
        game = toggle_candidate(game.id, self.host, self.cards[4].id, True, original_revision)
        game = toggle_candidate(game.id, self.host, self.cards[5].id, True, original_revision)
        toggle_candidate(game.id, self.guest, self.cards[6].id, True, original_revision)

        game = reset_candidates(game.id, self.host, original_revision)

        host_player = game.players.get(user=self.host)
        guest_player = game.players.get(user=self.guest)
        self.assertFalse(
            GuessWhoCandidateState.objects.filter(
                player=host_player,
                is_eliminated=True,
            ).exists()
        )
        self.assertTrue(
            GuessWhoCandidateState.objects.filter(
                player=guest_player,
                is_eliminated=True,
            ).exists()
        )
        self.assertEqual(game.turn_revision, original_revision)

    def test_reset_candidates_rejects_stale_revision_and_finished_game(self):
        game = self.make_started_game()
        game = toggle_candidate(game.id, self.host, self.cards[4].id, True, game.turn_revision)

        with self.assertRaises(StaleRevisionError):
            reset_candidates(game.id, self.host, game.turn_revision - 1)

        game = guess_pokemon(game.id, self.host, self.cards[1].id, game.turn_revision)
        with self.assertRaisesMessage(GuessWhoStateError, "terminée"):
            reset_candidates(game.id, self.host, game.turn_revision)

        self.assertTrue(
            GuessWhoCandidateState.objects.get(
                player__user=self.host,
                roster_card__pokemon_card=self.cards[4],
            ).is_eliminated
        )

    def test_state_never_discloses_opponent_target_before_game_end(self):
        game = self.make_started_game()

        host_state = serialize_game_state(game, self.host)
        guest_state = serialize_game_state(game, self.guest)
        host_by_id = {player["id"]: player for player in host_state["players"]}
        guest_by_id = {player["id"]: player for player in guest_state["players"]}
        host_player = game.players.get(user=self.host)
        guest_player = game.players.get(user=self.guest)

        self.assertEqual(host_by_id[host_player.id]["target"]["id"], self.cards[0].id)
        self.assertIsNone(host_by_id[guest_player.id]["target"])
        self.assertEqual(guest_by_id[guest_player.id]["target"]["id"], self.cards[1].id)
        self.assertIsNone(guest_by_id[host_player.id]["target"])

    def test_outsider_cannot_serialize_or_mutate_game(self):
        game = self.make_started_game()
        with self.assertRaises(GuessWhoPermissionError):
            serialize_game_state(game, self.outsider)
        with self.assertRaises(GuessWhoPermissionError):
            ask_question(game.id, self.outsider, "Puis-je tricher ?", game.turn_revision)

    def test_stale_revision_prevents_duplicate_turn(self):
        game = self.make_started_game()
        original_revision = game.turn_revision
        game = ask_question(game.id, self.host, "A-t-il des ailes ?", original_revision)

        with self.assertRaises(StaleRevisionError) as raised:
            ask_question(game.id, self.host, "A-t-il des ailes ?", original_revision)

        self.assertEqual(raised.exception.actual, game.turn_revision)
        self.assertEqual(GuessWhoTurn.objects.count(), 1)

    def test_serialized_contract_contains_tcg_type_and_complete_history(self):
        game = self.make_started_game()
        game = ask_question(game.id, self.host, "Est-il grand ?", game.turn_revision)
        game = answer_question(game.id, self.guest, True, game.turn_revision)
        state = serialize_game_state(game, self.host)

        self.assertEqual(
            set(state),
            {
                "game_id",
                "status",
                "turn_revision",
                "is_creator",
                "is_my_turn",
                "can_answer",
                "can_choose_target",
                "current_turn",
                "winner",
                "me",
                "players",
                "roster",
                "pending_question",
                "history",
            },
        )
        self.assertEqual(state["roster"][0]["tcg_type"], "grass")
        self.assertEqual(state["history"][0]["answer"], True)
        self.assertEqual(state["history"][0]["responder"]["username"], self.guest.username)


class ShippedCatalogTests(TestCase):
    """Le catalogue livré doit pouvoir alimenter un plateau, sinon le mode est
    hors service en production alors que les tests unitaires, qui construisent
    leur propre catalogue, restent verts."""

    def test_committed_fixture_holds_enough_species_for_a_roster(self):
        fixture_path = Path(settings.BASE_DIR) / "game" / "fixtures" / "pokemon_cards.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))

        species_count = len(data["cards"]) + len(data.get("catalogue", []))

        self.assertGreaterEqual(species_count, ROSTER_SIZE)

    def test_committed_fixture_leaves_room_for_random_rosters(self):
        fixture_path = Path(settings.BASE_DIR) / "game" / "fixtures" / "pokemon_cards.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))

        species_count = len(data["cards"]) + len(data.get("catalogue", []))

        # Un catalogue tout juste égal à ROSTER_SIZE donnerait le même plateau
        # à chaque partie : le tirage aléatoire n'aurait plus aucun effet.
        self.assertGreater(species_count, ROSTER_SIZE * 2)
