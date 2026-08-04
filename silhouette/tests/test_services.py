from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from game.pokemon_names import letter_hint, name_matches, normalize_name
from silhouette.models import SilhouetteGame, SilhouetteGuess
from silhouette.services import (
    LETTER_HINT_AFTER,
    MAX_POINTS,
    MIN_POINTS,
    REVEAL_SECONDS,
    ROUND_SECONDS,
    TYPE_HINT_AFTER,
    SilhouetteError,
    SilhouettePermissionError,
    advance_if_needed,
    create_game,
    current_round,
    join_game,
    points_for,
    serialize_game_state,
    start_game,
    submit_guess,
)

from .factories import make_gen_one_catalog, make_users


class SilhouetteFlowTests(TestCase):
    def setUp(self):
        self.cards = make_gen_one_catalog()
        self.host, self.guest, self.outsider = make_users(3)

    def make_started_game(self, round_count=5):
        game = create_game(self.host, round_count)
        join_game(game.id, self.guest)
        return start_game(game.id, self.host)

    def rewind(self, game, seconds):
        """Recule le départ de la manche : équivaut à laisser filer le temps."""
        round_obj = current_round(game)
        round_obj.started_at = timezone.now() - timedelta(seconds=seconds)
        round_obj.save(update_fields=["started_at"])
        return round_obj

    def test_round_count_must_be_one_of_the_offered_lengths(self):
        with self.assertRaises(SilhouetteError):
            create_game(self.host, 7)

    def test_created_game_registers_the_host_and_waits(self):
        game = create_game(self.host, 15)

        self.assertEqual(game.status, SilhouetteGame.Status.EN_ATTENTE)
        self.assertEqual(game.round_count, 15)
        self.assertEqual([player.user_id for player in game.players.all()], [self.host.id])

    def test_only_the_host_can_start(self):
        game = create_game(self.host, 5)
        join_game(game.id, self.guest)

        with self.assertRaises(SilhouettePermissionError):
            start_game(game.id, self.guest)

    def test_start_opens_a_first_round_on_a_gen_one_species(self):
        game = self.make_started_game()

        round_obj = current_round(game)
        self.assertEqual(game.status, SilhouetteGame.Status.EN_COURS)
        self.assertEqual(round_obj.number, 1)
        self.assertLessEqual(round_obj.pokemon_card.pokedex_id, 151)

    def test_nobody_can_join_a_started_game(self):
        game = self.make_started_game()

        with self.assertRaises(SilhouetteError):
            join_game(game.id, self.outsider)

    def test_a_correct_guess_scores_and_a_faster_one_scores_more(self):
        game = self.make_started_game()
        round_obj = self.rewind(game, 2)
        answer = round_obj.pokemon_card.name_fr

        result = submit_guess(game.id, self.host, answer)

        self.assertTrue(result["is_correct"])
        self.assertGreater(result["points"], points_for(20))
        self.assertEqual(game.players.get(user=self.host).score, result["points"])

    def test_points_decrease_with_time_and_never_fall_below_the_floor(self):
        self.assertEqual(points_for(0), MAX_POINTS)
        self.assertGreater(points_for(5), points_for(15))
        self.assertEqual(points_for(ROUND_SECONDS + 10), MIN_POINTS)

    def test_a_wrong_guess_scores_nothing_but_is_recorded(self):
        game = self.make_started_game()
        self.rewind(game, 1)

        result = submit_guess(game.id, self.host, "Ectoplasma-qui-n-existe-pas")

        self.assertFalse(result["is_correct"])
        self.assertEqual(game.players.get(user=self.host).score, 0)
        self.assertEqual(SilhouetteGuess.objects.filter(is_correct=False).count(), 1)

    def test_the_same_player_cannot_score_twice_in_a_round(self):
        game = self.make_started_game()
        round_obj = self.rewind(game, 1)

        submit_guess(game.id, self.host, round_obj.pokemon_card.name_fr)
        with self.assertRaises(SilhouetteError):
            submit_guess(game.id, self.host, round_obj.pokemon_card.name_fr)

    def test_a_guess_after_the_time_limit_is_refused(self):
        game = self.make_started_game()
        round_obj = self.rewind(game, ROUND_SECONDS + 1)

        with self.assertRaises(SilhouetteError):
            submit_guess(game.id, self.host, round_obj.pokemon_card.name_fr)

    def test_a_non_player_cannot_guess(self):
        game = self.make_started_game()

        with self.assertRaises(SilhouettePermissionError):
            submit_guess(game.id, self.outsider, "Pikachu")

    def test_the_round_reveals_when_every_player_found(self):
        game = self.make_started_game()
        round_obj = self.rewind(game, 1)
        answer = round_obj.pokemon_card.name_fr

        submit_guess(game.id, self.host, answer)
        self.assertIsNone(current_round(game).revealed_at)

        submit_guess(game.id, self.guest, answer)

        self.assertIsNotNone(current_round(game).revealed_at)

    def test_the_round_reveals_when_the_time_is_up(self):
        game = self.make_started_game()
        self.rewind(game, ROUND_SECONDS + 1)

        advance_if_needed(game.id)

        self.assertIsNotNone(current_round(game).revealed_at)

    def test_the_next_round_opens_after_the_reveal_pause(self):
        game = self.make_started_game()
        self.rewind(game, ROUND_SECONDS + 1)
        advance_if_needed(game.id)

        round_obj = current_round(game)
        round_obj.revealed_at = timezone.now() - timedelta(seconds=REVEAL_SECONDS + 1)
        round_obj.save(update_fields=["revealed_at"])
        advance_if_needed(game.id)

        self.assertEqual(current_round(game).number, 2)

    def test_the_game_ends_after_the_last_round(self):
        game = self.make_started_game(round_count=5)

        for _ in range(5):
            self.rewind(game, ROUND_SECONDS + 1)
            advance_if_needed(game.id)
            round_obj = current_round(game)
            round_obj.revealed_at = timezone.now() - timedelta(seconds=REVEAL_SECONDS + 1)
            round_obj.save(update_fields=["revealed_at"])
            advance_if_needed(game.id)
            game.refresh_from_db()

        self.assertEqual(game.status, SilhouetteGame.Status.TERMINEE)
        self.assertEqual(game.rounds.count(), 5)

    def test_a_round_never_repeats_a_species_while_the_catalogue_allows_it(self):
        game = self.make_started_game(round_count=5)

        for _ in range(4):
            self.rewind(game, ROUND_SECONDS + 1)
            advance_if_needed(game.id)
            round_obj = current_round(game)
            round_obj.revealed_at = timezone.now() - timedelta(seconds=REVEAL_SECONDS + 1)
            round_obj.save(update_fields=["revealed_at"])
            advance_if_needed(game.id)

        drawn = list(game.rounds.values_list("pokemon_card_id", flat=True))
        self.assertEqual(len(drawn), len(set(drawn)))


class SilhouetteStateTests(TestCase):
    def setUp(self):
        make_gen_one_catalog()
        self.host, self.guest = make_users(2)
        self.game = create_game(self.host, 5)
        join_game(self.game.id, self.guest)
        start_game(self.game.id, self.host)

    def rewind(self, seconds):
        round_obj = current_round(self.game)
        round_obj.started_at = timezone.now() - timedelta(seconds=seconds)
        round_obj.save(update_fields=["started_at"])
        return round_obj

    def test_the_answer_and_hints_stay_hidden_at_the_start(self):
        state = serialize_game_state(self.game, self.host)

        self.assertIsNone(state["round"]["answer"])
        self.assertIsNone(state["round"]["hints"]["type"])
        self.assertIsNone(state["round"]["hints"]["letters"])
        self.assertNotIn("pokemon_card", state["round"])

    def test_the_type_hint_appears_after_five_seconds(self):
        self.rewind(TYPE_HINT_AFTER + 1)

        state = serialize_game_state(self.game, self.host)

        self.assertTrue(state["round"]["hints"]["type"])
        self.assertIsNone(state["round"]["hints"]["letters"])

    def test_the_letter_hint_appears_after_ten_seconds(self):
        round_obj = self.rewind(LETTER_HINT_AFTER + 1)

        state = serialize_game_state(self.game, self.host)

        hints = state["round"]["hints"]
        self.assertEqual(hints["letters"], letter_hint(round_obj.pokemon_card.name_fr))
        self.assertEqual(hints["letter_count"], sum(1 for c in round_obj.pokemon_card.name_fr if c.isalpha()))

    def test_wrong_guesses_stay_private_while_finds_are_public(self):
        round_obj = self.rewind(1)
        submit_guess(self.game.id, self.guest, "Raté")
        submit_guess(self.game.id, self.guest, round_obj.pokemon_card.name_fr)

        host_state = serialize_game_state(self.game, self.host)

        self.assertEqual(host_state["round"]["my_guesses"], [])
        self.assertEqual(len(host_state["round"]["found"]), 1)
        self.assertEqual(host_state["round"]["found"][0]["username"], self.guest.get_username())

    def test_the_answer_is_exposed_once_revealed(self):
        round_obj = self.rewind(ROUND_SECONDS + 1)
        advance_if_needed(self.game.id)
        self.game.refresh_from_db()

        state = serialize_game_state(self.game, self.host)

        self.assertTrue(state["round"]["revealed"])
        self.assertEqual(state["round"]["answer"], round_obj.pokemon_card.name_fr)


class PokemonNameTests(TestCase):
    def test_normalization_ignores_case_accents_and_punctuation(self):
        self.assertEqual(normalize_name("  Électhor "), normalize_name("electhor"))
        self.assertEqual(normalize_name("M. Mime"), "mmime")
        self.assertEqual(normalize_name("Nidoran♀"), "nidoran")

    def test_both_french_and_english_names_are_accepted(self):
        card = make_gen_one_catalog(1)[0]
        card.name_fr = "Bulbizarre"
        card.name_en = "Bulbasaur"

        self.assertTrue(name_matches("bulbizarre", card))
        self.assertTrue(name_matches("BULBASAUR", card))
        self.assertFalse(name_matches("herbizarre", card))
        self.assertFalse(name_matches("", card))

    def test_letter_hint_keeps_only_the_first_and_last_letters(self):
        self.assertEqual(letter_hint("Pikachu"), "P • • • • • u")
        self.assertEqual(letter_hint("Ho"), "Ho")
