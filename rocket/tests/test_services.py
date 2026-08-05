from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from rocket.models import RocketGame, RocketPlayer
from rocket.services import (
    RocketError,
    RocketPermissionError,
    advance_if_expired,
    create_game,
    join_game,
    rocket_count_for,
    send_message,
    serialize_game_state,
    start_game,
    start_vote,
    submit_night_action,
    submit_vote,
)

User = get_user_model()


class RocketGameServiceTests(TestCase):
    def setUp(self):
        self.users = [User.objects.create_user(username=f"agent-{index}") for index in range(12)]
        self.game = create_game(self.users[0])
        for user in self.users[1:6]:
            join_game(self.game.id, user)

    def start_deterministically(self):
        with patch("rocket.services.random.shuffle", side_effect=lambda values: None):
            start_game(self.game.id, self.users[0])
        self.game.refresh_from_db()
        return list(self.game.players.order_by("turn_order"))

    def revision(self):
        self.game.refresh_from_db()
        return self.game.turn_revision

    def test_rocket_count_scales_with_room_size(self):
        self.assertEqual(rocket_count_for(6), 1)
        self.assertEqual(rocket_count_for(8), 2)
        self.assertEqual(rocket_count_for(11), 3)

    def test_only_host_can_start_and_six_players_are_required(self):
        with self.assertRaises(RocketPermissionError):
            start_game(self.game.id, self.users[1])

        short_game = create_game(self.users[7])
        with self.assertRaisesMessage(RocketError, "au moins 6"):
            start_game(short_game.id, self.users[7])

    def test_start_assigns_one_rocket_detective_guardian_and_trainers(self):
        players = self.start_deterministically()
        self.assertEqual(players[0].role, RocketPlayer.Role.ROCKET)
        self.assertEqual(players[1].role, RocketPlayer.Role.DETECTIVE)
        self.assertEqual(players[2].role, RocketPlayer.Role.GUARDIAN)
        self.assertEqual([player.role for player in players[3:]], [RocketPlayer.Role.TRAINER] * 3)
        self.assertEqual(self.game.status, RocketGame.Status.NUIT)
        self.assertEqual(self.game.round_number, 1)

    def test_serialization_never_leaks_hidden_roles(self):
        players = self.start_deterministically()
        rocket_state = serialize_game_state(self.game, self.users[0])
        detective_state = serialize_game_state(self.game, self.users[1])

        self.assertEqual(rocket_state["players"][0]["role"]["key"], RocketPlayer.Role.ROCKET)
        self.assertIsNone(rocket_state["players"][1]["role"])
        self.assertEqual(detective_state["players"][1]["role"]["key"], RocketPlayer.Role.DETECTIVE)
        self.assertIsNone(detective_state["players"][0]["role"])
        self.assertNotIn("role", detective_state["players"][3]["username"].lower())
        self.assertEqual(players[0].role, RocketPlayer.Role.ROCKET)
        self.assertNotIn("required", detective_state["night"])
        self.assertNotIn("submitted", detective_state["night"])
        self.assertNotIn("submitted_player_ids", detective_state["vote"])

    def test_mutations_require_an_exact_revision(self):
        players = self.start_deterministically()
        with self.assertRaisesMessage(RocketError, "obligatoire"):
            submit_night_action(self.game.id, self.users[0], players[3].id, None)

    def test_night_actions_resolve_protection_and_keep_inspection_private(self):
        players = self.start_deterministically()
        victim = players[3]

        submit_night_action(self.game.id, self.users[0], victim.id, self.revision())
        submit_night_action(self.game.id, self.users[1], players[0].id, self.revision())
        submit_night_action(self.game.id, self.users[2], victim.id, self.revision())

        self.game.refresh_from_db()
        victim.refresh_from_db()
        self.assertTrue(victim.is_alive)
        self.assertEqual(self.game.status, RocketGame.Status.DISCUSSION)
        self.assertTrue(self.game.last_event["attack_blocked"])

        detective = serialize_game_state(self.game, self.users[1])
        trainer = serialize_game_state(self.game, self.users[3])
        self.assertTrue(detective["night"]["detective_results"][0]["is_rocket"])
        self.assertEqual(trainer["night"]["detective_results"], [])

    def test_trainers_cannot_act_at_night(self):
        players = self.start_deterministically()
        with self.assertRaises(RocketPermissionError):
            submit_night_action(self.game.id, self.users[3], players[0].id, self.revision())

    def _reach_discussion(self):
        players = self.start_deterministically()
        submit_night_action(self.game.id, self.users[0], players[3].id, self.revision())
        submit_night_action(self.game.id, self.users[1], players[0].id, self.revision())
        submit_night_action(self.game.id, self.users[2], players[3].id, self.revision())
        self.game.refresh_from_db()
        return players

    def test_chat_is_normalized_and_limited_to_living_players_in_discussion(self):
        self._reach_discussion()
        message = send_message(self.game.id, self.users[4], "  Je   soupçonne   agent-0. ", self.revision())
        self.assertEqual(message.body, "Je soupçonne agent-0.")
        with self.assertRaises(RocketError):
            send_message(self.game.id, self.users[4], "x" * 301, self.revision())

    def test_vote_eliminates_unique_leader_then_opens_next_night(self):
        players = self._reach_discussion()
        start_vote(self.game.id, self.users[0], self.revision())
        target = players[5]
        for player in players:
            if player.id == target.id:
                submit_vote(self.game.id, player.user, players[4].id, self.revision())
            else:
                submit_vote(self.game.id, player.user, target.id, self.revision())

        self.game.refresh_from_db()
        target.refresh_from_db()
        self.assertFalse(target.is_alive)
        self.assertEqual(self.game.status, RocketGame.Status.NUIT)
        self.assertEqual(self.game.round_number, 2)

    def test_any_living_player_can_open_vote_if_host_is_unavailable(self):
        self._reach_discussion()
        host_player = self.game.players.get(user=self.users[0])
        host_player.is_alive = False
        host_player.save(update_fields=["is_alive"])
        start_vote(self.game.id, self.users[1], self.revision())
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, RocketGame.Status.VOTE)

    def test_expired_night_autocompletes_missing_actions(self):
        self.start_deterministically()
        self.game.phase_deadline = timezone.now() - timezone.timedelta(seconds=1)
        self.game.save(update_fields=["phase_deadline"])
        advance_if_expired(self.game.id)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, RocketGame.Status.DISCUSSION)
        self.assertEqual(self.game.night_actions.filter(round_number=1).count(), 3)

    def test_tied_vote_eliminates_nobody(self):
        players = self._reach_discussion()
        start_vote(self.game.id, self.users[0], self.revision())
        targets = [players[3], players[4]]
        for index, player in enumerate(players):
            target = targets[index % 2]
            if target.id == player.id:
                target = targets[(index + 1) % 2]
                if target.id == player.id:
                    target = players[5]
            submit_vote(self.game.id, player.user, target.id, self.revision())
        self.game.refresh_from_db()
        self.assertTrue(self.game.last_event["tie"])
        self.assertEqual(self.game.status, RocketGame.Status.NUIT)

    def test_eliminating_last_rocket_finishes_for_allies_and_records_stats(self):
        players = self._reach_discussion()
        start_vote(self.game.id, self.users[0], self.revision())
        rocket = players[0]
        for player in players:
            target = players[3] if player.id == rocket.id else rocket
            submit_vote(self.game.id, player.user, target.id, self.revision())

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, RocketGame.Status.TERMINEE)
        self.assertEqual(self.game.winner_side, RocketGame.WinnerSide.ALLIES)
        finished_state = serialize_game_state(self.game, self.users[3])
        self.assertTrue(all(player["role"] is not None for player in finished_state["players"]))
        self.users[3].profile.refresh_from_db()
        self.users[0].profile.refresh_from_db()
        self.assertEqual(self.users[3].profile.total_games_won, 1)
        self.assertEqual(self.users[0].profile.total_games_won, 0)
        self.assertEqual(self.users[0].profile.total_games_played, 1)


class RocketLobbyServiceTests(TestCase):
    def test_room_is_capped_at_twelve(self):
        users = [User.objects.create_user(username=f"full-{index}") for index in range(13)]
        game = create_game(users[0])
        for user in users[1:12]:
            join_game(game.id, user)
        with self.assertRaisesMessage(RocketError, "complète"):
            join_game(game.id, users[12])
