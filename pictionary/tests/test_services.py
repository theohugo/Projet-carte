from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from pictionary.models import PictionaryGame, PictionaryStroke
from pictionary.services import (
    DRAWER_POINTS_PER_FINDER,
    MAX_POINTS_PER_STROKE,
    REVEAL_SECONDS,
    ROUND_SECONDS,
    PictionaryError,
    PictionaryPermissionError,
    add_stroke,
    advance_if_needed,
    create_game,
    current_round,
    join_game,
    points_for,
    serialize_game_state,
    start_game,
    submit_guess,
)
from silhouette.tests.factories import make_gen_one_catalog, make_users


class PictionaryFlowTests(TestCase):
    def setUp(self):
        make_gen_one_catalog()
        self.host, self.guest, self.outsider = make_users(3)

    def make_started_game(self, round_count=3):
        game = create_game(self.host, round_count)
        join_game(game.id, self.guest)
        return start_game(game.id, self.host)

    def rewind(self, game, seconds):
        round_obj = current_round(game)
        round_obj.started_at = timezone.now() - timedelta(seconds=seconds)
        round_obj.save(update_fields=["started_at"])
        return round_obj

    def test_a_single_player_cannot_start(self):
        game = create_game(self.host, 3)

        with self.assertRaisesMessage(PictionaryError, "au moins 2 joueurs"):
            start_game(game.id, self.host)

    def test_only_the_host_can_start(self):
        game = create_game(self.host, 3)
        join_game(game.id, self.guest)

        with self.assertRaises(PictionaryPermissionError):
            start_game(game.id, self.guest)

    def test_the_first_round_gives_the_pencil_to_the_first_player(self):
        game = self.make_started_game()

        round_obj = current_round(game)
        self.assertEqual(game.status, PictionaryGame.Status.EN_COURS)
        self.assertEqual(round_obj.drawer.user_id, self.host.id)
        self.assertLessEqual(round_obj.pokemon_card.pokedex_id, 151)

    def test_the_pencil_rotates_at_each_round(self):
        game = self.make_started_game(round_count=3)
        drawers = [current_round(game).drawer.user_id]

        for _ in range(2):
            self.rewind(game, ROUND_SECONDS + 1)
            advance_if_needed(game.id)
            round_obj = current_round(game)
            round_obj.ended_at = timezone.now() - timedelta(seconds=REVEAL_SECONDS + 1)
            round_obj.save(update_fields=["ended_at"])
            advance_if_needed(game.id)
            drawers.append(current_round(game).drawer.user_id)

        self.assertEqual(drawers, [self.host.id, self.guest.id, self.host.id])

    def test_only_the_drawer_may_draw(self):
        game = self.make_started_game()

        with self.assertRaises(PictionaryPermissionError):
            add_stroke(game.id, self.guest, {"points": [[0.1, 0.1], [0.2, 0.2]]})

        sequence = add_stroke(game.id, self.host, {"points": [[0.1, 0.1], [0.2, 0.2]]})
        self.assertEqual(sequence, 1)

    def test_stroke_sequences_increase_and_a_clear_is_recorded(self):
        game = self.make_started_game()

        add_stroke(game.id, self.host, {"points": [[0.1, 0.1]]})
        add_stroke(game.id, self.host, {"points": [[0.4, 0.4]]})
        add_stroke(game.id, self.host, {"is_clear": True})

        strokes = list(current_round(game).strokes.all())
        self.assertEqual([stroke.sequence for stroke in strokes], [1, 2, 3])
        self.assertTrue(strokes[-1].is_clear)
        self.assertEqual(strokes[-1].points, [])

    def test_stroke_payloads_are_clamped_and_sanitized(self):
        game = self.make_started_game()

        add_stroke(
            game.id,
            self.host,
            {
                "points": [[-3, 4], [0.5, 0.5], ["x", 0.2], [0.25]],
                "color": "javascript:alert(1)",
                "width": 900,
            },
        )

        stroke = PictionaryStroke.objects.get()
        self.assertEqual(stroke.points, [[0.0, 1.0], [0.5, 0.5]])
        self.assertEqual(stroke.color, "#f6f9ff")
        self.assertEqual(stroke.width, 24)

    def test_an_oversized_stroke_is_truncated(self):
        game = self.make_started_game()

        add_stroke(game.id, self.host, {"points": [[0.5, 0.5]] * (MAX_POINTS_PER_STROKE + 50)})

        self.assertEqual(len(PictionaryStroke.objects.get().points), MAX_POINTS_PER_STROKE)

    def test_the_drawer_cannot_guess(self):
        game = self.make_started_game()
        answer = current_round(game).pokemon_card.name_fr

        with self.assertRaises(PictionaryError):
            submit_guess(game.id, self.host, answer)

    def test_a_correct_guess_scores_the_guesser_and_the_drawer(self):
        game = self.make_started_game()
        round_obj = self.rewind(game, 3)

        result = submit_guess(game.id, self.guest, round_obj.pokemon_card.name_fr)

        self.assertTrue(result["is_correct"])
        self.assertEqual(game.players.get(user=self.guest).score, result["points"])
        self.assertEqual(game.players.get(user=self.host).score, DRAWER_POINTS_PER_FINDER)

    def test_points_decrease_with_time(self):
        self.assertGreater(points_for(1), points_for(45))
        self.assertEqual(points_for(ROUND_SECONDS * 2), points_for(ROUND_SECONDS))

    def test_the_round_ends_once_every_guesser_found(self):
        game = self.make_started_game()
        round_obj = self.rewind(game, 2)

        submit_guess(game.id, self.guest, round_obj.pokemon_card.name_fr)

        self.assertIsNotNone(current_round(game).ended_at)

    def test_the_game_ends_after_the_last_round(self):
        game = self.make_started_game(round_count=3)

        for _ in range(3):
            self.rewind(game, ROUND_SECONDS + 1)
            advance_if_needed(game.id)
            round_obj = current_round(game)
            round_obj.ended_at = timezone.now() - timedelta(seconds=REVEAL_SECONDS + 1)
            round_obj.save(update_fields=["ended_at"])
            advance_if_needed(game.id)
            game.refresh_from_db()

        self.assertEqual(game.status, PictionaryGame.Status.TERMINEE)
        self.assertEqual(game.rounds.count(), 3)


class PictionaryStateTests(TestCase):
    def setUp(self):
        make_gen_one_catalog()
        self.host, self.guest = make_users(2)
        self.game = create_game(self.host, 3)
        join_game(self.game.id, self.guest)
        start_game(self.game.id, self.host)

    def test_the_word_reaches_the_drawer_only(self):
        drawer_state = serialize_game_state(self.game, self.host)
        guesser_state = serialize_game_state(self.game, self.guest)

        self.assertTrue(drawer_state["round"]["am_drawer"])
        self.assertEqual(drawer_state["round"]["word"], current_round(self.game).pokemon_card.name_fr)
        self.assertFalse(guesser_state["round"]["am_drawer"])
        self.assertIsNone(guesser_state["round"]["word"])

    def test_the_word_is_public_once_the_round_ended(self):
        round_obj = current_round(self.game)
        round_obj.ended_at = timezone.now()
        round_obj.save(update_fields=["ended_at"])

        guesser_state = serialize_game_state(self.game, self.guest)

        self.assertTrue(guesser_state["round"]["ended"])
        self.assertEqual(guesser_state["round"]["word"], round_obj.pokemon_card.name_fr)

    def test_strokes_are_sent_incrementally(self):
        add_stroke(self.game.id, self.host, {"points": [[0.1, 0.1]]})
        add_stroke(self.game.id, self.host, {"points": [[0.2, 0.2]]})

        full = serialize_game_state(self.game, self.guest)
        partial = serialize_game_state(self.game, self.guest, since_sequence=1)

        self.assertEqual([stroke["sequence"] for stroke in full["round"]["strokes"]], [1, 2])
        self.assertEqual([stroke["sequence"] for stroke in partial["round"]["strokes"]], [2])
        self.assertEqual(partial["round"]["last_sequence"], 2)

    def test_wrong_guesses_stay_private(self):
        submit_guess(self.game.id, self.guest, "Complètement à côté")

        guesser_state = serialize_game_state(self.game, self.guest)
        drawer_state = serialize_game_state(self.game, self.host)

        self.assertEqual(len(guesser_state["round"]["my_guesses"]), 1)
        self.assertEqual(drawer_state["round"]["my_guesses"], [])
        self.assertEqual(drawer_state["round"]["found"], [])
