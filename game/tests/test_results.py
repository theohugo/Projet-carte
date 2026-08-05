from django.contrib.auth import get_user_model
from django.test import TestCase

from game.quests import quest_board
from game.results import record_completed_game

User = get_user_model()


class CompletedGameResultTests(TestCase):
    def test_stats_and_quests_are_recorded_for_players_and_winners(self):
        winner = User.objects.create_user(username="winner")
        loser = User.objects.create_user(username="loser")

        record_completed_game([winner, loser], {winner.id})

        winner.profile.refresh_from_db()
        loser.profile.refresh_from_db()
        self.assertEqual(winner.profile.total_games_played, 1)
        self.assertEqual(winner.profile.total_games_won, 1)
        self.assertEqual(loser.profile.total_games_played, 1)
        self.assertEqual(loser.profile.total_games_won, 0)
        self.assertEqual(quest_board(winner)["daily"][0]["progress"], 1)
