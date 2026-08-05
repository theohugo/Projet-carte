from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.utils.translation import override

from game.pokemon_names import letter_hint, name_matches, normalize_name
from silhouette.models import SilhouetteGame, SilhouetteGuess
from silhouette.services import (
    LETTER_HINT_AFTER,
    MAX_BOTS,
    MAX_POINTS,
    MIN_POINTS,
    REVEAL_SECONDS,
    ROUND_SECONDS,
    TYPE_HINT_AFTER,
    SilhouetteError,
    SilhouettePermissionError,
    add_bot,
    advance_if_needed,
    create_game,
    current_round,
    join_game,
    points_for,
    remove_bot,
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

    def test_only_the_host_can_manage_bots_while_waiting(self):
        game = create_game(self.host, 5)

        with self.assertRaises(SilhouettePermissionError):
            add_bot(game.id, self.guest)

        bot = add_bot(game.id, self.host)
        self.assertTrue(bot.is_bot)
        self.assertTrue(bot.display_name.startswith("IA "))

        with self.assertRaises(SilhouettePermissionError):
            remove_bot(game.id, self.guest, bot.id)

        remove_bot(game.id, self.host, bot.id)
        self.assertFalse(game.players.filter(pk=bot.pk).exists())

    def test_bot_display_name_and_payload_follow_active_language(self):
        game = create_game(self.host, 5)
        bot = add_bot(game.id, self.host)

        with override("fr"):
            self.assertEqual(bot.display_name, "IA Zorua")
            self.assertEqual(
                next(
                    player for player in serialize_game_state(game, self.host)["players"] if player["is_bot"]
                )["username"],
                "IA Zorua",
            )
        with override("en"):
            self.assertEqual(bot.display_name, "Zorua AI")
            self.assertEqual(
                next(
                    player for player in serialize_game_state(game, self.host)["players"] if player["is_bot"]
                )["username"],
                "Zorua AI",
            )

    def test_a_room_enforces_the_bot_limit(self):
        game = create_game(self.host, 5)
        for _ in range(MAX_BOTS):
            add_bot(game.id, self.host)

        with self.assertRaises(SilhouetteError):
            add_bot(game.id, self.host)

        state = serialize_game_state(game, self.host)
        self.assertEqual(state["bot_count"], MAX_BOTS)
        self.assertFalse(state["can_add_bot"])

    def test_bots_cannot_be_changed_after_start(self):
        game = create_game(self.host, 5)
        bot = add_bot(game.id, self.host)
        start_game(game.id, self.host)

        with self.assertRaises(SilhouetteError):
            add_bot(game.id, self.host)
        with self.assertRaises(SilhouetteError):
            remove_bot(game.id, self.host, bot.id)

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

    def test_a_bot_answers_after_a_delay_without_leaking_the_species(self):
        game = create_game(self.host, 5)
        bot = add_bot(game.id, self.host)
        start_game(game.id, self.host)
        round_obj = self.rewind(game, 21)

        advance_if_needed(game.id)

        guess = round_obj.guesses.get(player=bot, is_correct=True)
        self.assertGreater(guess.points, 0)
        state = serialize_game_state(game, self.host)
        self.assertIsNone(state["round"]["answer"])
        self.assertNotIn(round_obj.pokemon_card.name_fr, str(state))
        self.assertIn(bot.display_name, [entry["username"] for entry in state["round"]["found"]])

    def test_due_bot_answers_allow_the_round_to_finish(self):
        game = create_game(self.host, 5)
        add_bot(game.id, self.host)
        start_game(game.id, self.host)
        round_obj = self.rewind(game, 21)
        submit_guess(game.id, self.host, round_obj.pokemon_card.name_fr)

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

        type_hints = state["round"]["hints"]["type"]
        self.assertTrue(type_hints)
        self.assertEqual(type_hints[0]["name"], type_hints[0]["name_fr"])
        self.assertIn(
            f"game/img/types/{type_hints[0]['slug']}.png",
            type_hints[0]["icon_url"],
        )
        self.assertIsNone(state["round"]["hints"]["letters"])

    def test_the_type_hint_uses_english_names_without_changing_its_png(self):
        self.rewind(TYPE_HINT_AFTER + 1)

        with override("en"):
            state = serialize_game_state(self.game, self.host)

        type_hint = state["round"]["hints"]["type"][0]
        self.assertEqual(type_hint["name"], type_hint["name_en"])
        self.assertIn(
            f"game/img/types/{type_hint['slug']}.png",
            type_hint["icon_url"],
        )

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
