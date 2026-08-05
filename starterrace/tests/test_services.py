from django.test import TestCase

from starterrace.models import Game, Move, Pawn
from starterrace.services import (
    FINISH_POSITION,
    MAX_PLAYERS,
    SHORTCUTS,
    StaleRevisionError,
    StarterRaceError,
    StarterRacePermissionError,
    StarterRaceStateError,
    create_game,
    global_position,
    join_game,
    move_pawn,
    roll_dice,
    serialize_game_state,
    start_game,
)

from .factories import FixedRng, make_starter_catalog, make_users


class StarterRaceFlowTests(TestCase):
    def setUp(self):
        self.cards = make_starter_catalog()
        self.host, self.guest, self.third, self.fourth, self.outsider = make_users()

    def make_started_game(self):
        game = create_game(self.host)
        join_game(game.id, self.guest)
        return start_game(game.id, self.host)

    def test_creation_assigns_real_bulbasaur_artwork_and_four_pawns(self):
        game = create_game(self.host)

        player = game.players.select_related("starter_card").get()
        self.assertEqual(player.starter_card.pokedex_id, 1)
        self.assertEqual(player.starter_card.name_fr, "Bulbizarre")
        self.assertIn("official-artwork/1.png", player.starter_card.sprite_url)
        self.assertEqual(
            list(player.pawns.values_list("number", "position")), [(0, -1), (1, -1), (2, -1), (3, -1)]
        )

    def test_joiners_receive_the_four_distinct_starters_and_the_room_caps_at_four(self):
        game = create_game(self.host)
        for user in (self.guest, self.third, self.fourth):
            join_game(game.id, user)

        self.assertEqual(game.players.count(), MAX_PLAYERS)
        self.assertEqual(
            list(game.players.values_list("starter_card__pokedex_id", flat=True)),
            [1, 4, 7, 25],
        )
        with self.assertRaisesMessage(StarterRaceStateError, "complète"):
            join_game(game.id, self.outsider)

    def test_only_host_can_start_and_two_players_are_required(self):
        game = create_game(self.host)
        with self.assertRaisesMessage(StarterRaceStateError, "au moins 2"):
            start_game(game.id, self.host)

        join_game(game.id, self.guest)
        with self.assertRaises(StarterRacePermissionError):
            start_game(game.id, self.guest)

        game = start_game(game.id, self.host)
        self.assertEqual(game.status, Game.Status.EN_COURS)
        self.assertEqual(game.current_turn.user, self.host)

    def test_injected_rng_sets_a_server_roll_between_one_and_six(self):
        game = self.make_started_game()

        game = roll_dice(game.id, self.host, game.turn_revision, rng=FixedRng(6))

        self.assertEqual(game.pending_roll, 6)
        second_game = create_game(self.host)
        join_game(second_game.id, self.guest)
        second_game = start_game(second_game.id, self.host)
        with self.assertRaisesMessage(StarterRaceError, "entre 1 et 6"):
            roll_dice(second_game.id, self.host, second_game.turn_revision, rng=lambda: 9)

    def test_a_six_releases_a_pawn_and_keeps_the_turn(self):
        game = self.make_started_game()
        game = roll_dice(game.id, self.host, game.turn_revision, rng=FixedRng(6))
        pawn = game.players.get(user=self.host).pawns.first()

        game = move_pawn(game.id, self.host, pawn.id, game.turn_revision)

        pawn.refresh_from_db()
        self.assertEqual(pawn.position, 0)
        self.assertEqual(game.current_turn.user, self.host)
        self.assertIsNone(game.pending_roll)
        self.assertTrue(game.moves.get().grants_extra_turn)

    def test_a_normal_move_advances_then_passes_to_next_player(self):
        game = self.make_started_game()
        pawn = game.players.get(user=self.host).pawns.first()
        pawn.position = 10
        pawn.save(update_fields=["position"])
        game = roll_dice(game.id, self.host, game.turn_revision, rng=FixedRng(2))

        game = move_pawn(game.id, self.host, pawn.id, game.turn_revision)

        pawn.refresh_from_db()
        self.assertEqual(pawn.position, 12)
        self.assertEqual(game.current_turn.user, self.guest)

    def test_a_roll_with_no_legal_pawn_is_logged_and_passes_automatically(self):
        game = self.make_started_game()

        game = roll_dice(game.id, self.host, game.turn_revision, rng=FixedRng(4))

        entry = Move.objects.get(game=game)
        self.assertTrue(entry.was_pass)
        self.assertEqual(entry.roll, 4)
        self.assertEqual(game.current_turn.user, self.guest)
        self.assertIsNone(game.pending_roll)

    def test_a_six_with_no_legal_pawn_would_give_another_roll(self):
        game = self.make_started_game()
        player = game.players.get(user=self.host)
        player.pawns.update(position=FINISH_POSITION)

        game = roll_dice(game.id, self.host, game.turn_revision, rng=FixedRng(6))

        self.assertEqual(game.current_turn_id, player.id)
        self.assertTrue(game.moves.get().grants_extra_turn)

    def test_a_pawn_must_reach_the_finish_exactly(self):
        game = self.make_started_game()
        player = game.players.get(user=self.host)
        player.pawns.update(position=FINISH_POSITION)
        pawn = player.pawns.first()
        pawn.position = FINISH_POSITION - 1
        pawn.save(update_fields=["position"])

        # Un 2 dépasse la Ligue : aucun pion n'est légal et le tour passe.
        game = roll_dice(game.id, self.host, game.turn_revision, rng=FixedRng(2))
        pawn.refresh_from_db()
        self.assertEqual(pawn.position, FINISH_POSITION - 1)
        self.assertTrue(game.moves.get().was_pass)

    def test_fourth_exact_arrival_wins_the_game(self):
        game = self.make_started_game()
        player = game.players.get(user=self.host)
        player.pawns.update(position=FINISH_POSITION)
        pawn = player.pawns.first()
        pawn.position = FINISH_POSITION - 1
        pawn.save(update_fields=["position"])
        game = roll_dice(game.id, self.host, game.turn_revision, rng=FixedRng(1))

        game = move_pawn(game.id, self.host, pawn.id, game.turn_revision)

        self.assertEqual(game.status, Game.Status.TERMINEE)
        self.assertEqual(game.winner_id, player.id)
        self.assertIsNone(game.current_turn)
        self.assertIsNotNone(game.finished_at)


class ShortcutAndCaptureTests(TestCase):
    def setUp(self):
        make_starter_catalog()
        self.host, self.guest = make_users(2)
        self.game = create_game(self.host)
        join_game(self.game.id, self.guest)
        self.game = start_game(self.game.id, self.host)
        self.host_player = self.game.players.get(user=self.host)
        self.guest_player = self.game.players.get(user=self.guest)

    def test_landing_on_a_shortcut_advances_four_extra_cells(self):
        pawn = self.host_player.pawns.first()
        pawn.position = 0
        pawn.save(update_fields=["position"])
        game = roll_dice(self.game.id, self.host, self.game.turn_revision, rng=FixedRng(3))

        game = move_pawn(game.id, self.host, pawn.id, game.turn_revision)

        pawn.refresh_from_db()
        entry = Move.objects.get(game=game)
        self.assertEqual(pawn.position, 7)
        self.assertEqual((entry.shortcut_from, entry.shortcut_to), (3, SHORTCUTS[3]))

    def test_capture_after_a_shortcut_returns_the_opponent_home(self):
        attacker = self.host_player.pawns.first()
        attacker.position = 0
        attacker.save(update_fields=["position"])
        victim = self.guest_player.pawns.first()
        victim.position = 37  # Départ 10 + 37 = case globale 7.
        victim.save(update_fields=["position"])
        self.assertEqual(global_position(self.guest_player, victim.position), 7)
        game = roll_dice(self.game.id, self.host, self.game.turn_revision, rng=FixedRng(3))

        game = move_pawn(game.id, self.host, attacker.id, game.turn_revision)

        victim.refresh_from_db()
        entry = Move.objects.get(game=game)
        self.assertEqual(victim.position, Pawn.HOME)
        self.assertEqual(entry.captured_pawns[0]["username"], self.guest.username)

    def test_a_refuge_prevents_capture(self):
        attacker = self.host_player.pawns.first()
        attacker.position = 0
        attacker.save(update_fields=["position"])
        victim = self.guest_player.pawns.first()
        victim.position = 35  # Case globale 5, un refuge.
        victim.save(update_fields=["position"])
        game = roll_dice(self.game.id, self.host, self.game.turn_revision, rng=FixedRng(5))

        game = move_pawn(game.id, self.host, attacker.id, game.turn_revision)

        victim.refresh_from_db()
        self.assertEqual(victim.position, 35)
        self.assertEqual(game.moves.get().captured_pawns, [])


class RevisionPermissionAndStateTests(TestCase):
    def setUp(self):
        make_starter_catalog()
        self.host, self.guest, self.outsider = make_users(3)
        self.game = create_game(self.host)
        join_game(self.game.id, self.guest)
        self.game = start_game(self.game.id, self.host)

    def test_stale_revision_prevents_a_duplicate_roll(self):
        original_revision = self.game.turn_revision
        game = roll_dice(self.game.id, self.host, original_revision, rng=FixedRng(6))

        with self.assertRaises(StaleRevisionError) as raised:
            roll_dice(self.game.id, self.host, original_revision, rng=FixedRng(6))

        self.assertEqual(raised.exception.actual, game.turn_revision)
        self.assertEqual(game.pending_roll, 6)

    def test_opponent_cannot_roll_or_move_the_current_players_pawn(self):
        with self.assertRaises(StarterRacePermissionError):
            roll_dice(self.game.id, self.guest, self.game.turn_revision, rng=FixedRng(6))

        game = roll_dice(self.game.id, self.host, self.game.turn_revision, rng=FixedRng(6))
        host_pawn = game.players.get(user=self.host).pawns.first()
        with self.assertRaises(StarterRacePermissionError):
            move_pawn(game.id, self.guest, host_pawn.id, game.turn_revision)

    def test_state_is_participant_only_and_whitelists_public_profile_fields(self):
        with self.assertRaises(StarterRacePermissionError):
            serialize_game_state(self.game, self.outsider)

        payload = serialize_game_state(self.game, self.host)
        serialized = str(payload)
        self.assertNotIn(self.host.email, serialized)
        self.assertNotIn(self.guest.email, serialized)
        self.assertNotIn("password", serialized)
        self.assertEqual(payload["players"][0]["starter"]["name"], "Bulbizarre")
        self.assertEqual(len(payload["players"][0]["pawns"]), 4)
        self.assertEqual(payload["board"]["track_length"], 40)
        self.assertEqual(payload["board"]["final_lane_length"], 4)
