from django.db import IntegrityError, transaction
from django.test import TestCase

from game.models import GamePlayer
from game.tests.factories import make_game, make_users


class GamePlayerConstraintTests(TestCase):
    def setUp(self):
        self.users = make_users(2)
        self.game = make_game(self.users[0])

    def test_same_user_cannot_join_twice(self):
        GamePlayer.objects.create(game=self.game, user=self.users[0], turn_order=0)
        with self.assertRaises(IntegrityError):
            GamePlayer.objects.create(game=self.game, user=self.users[0], turn_order=1)

    def test_turn_order_unique_per_game(self):
        GamePlayer.objects.create(game=self.game, user=self.users[0], turn_order=0)
        with self.assertRaises(IntegrityError):
            GamePlayer.objects.create(game=self.game, user=self.users[1], turn_order=0)

    def test_bot_has_a_name_and_no_user(self):
        bot = GamePlayer.objects.create(
            game=self.game,
            user=None,
            bot_name="IA Porygon",
            turn_order=0,
        )

        self.assertTrue(bot.is_bot)
        self.assertEqual(bot.display_name, "IA Porygon")

    def test_player_cannot_have_neither_user_nor_bot_name(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GamePlayer.objects.create(game=self.game, turn_order=0)

    def test_player_cannot_have_both_user_and_bot_name(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GamePlayer.objects.create(
                game=self.game,
                user=self.users[0],
                bot_name="IA Porygon",
                turn_order=0,
            )

    def test_bot_names_are_unique_inside_a_game(self):
        GamePlayer.objects.create(
            game=self.game,
            bot_name="IA Porygon",
            turn_order=0,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            GamePlayer.objects.create(
                game=self.game,
                bot_name="IA Porygon",
                turn_order=1,
            )


class ProfileAutoCreationTests(TestCase):
    def test_profile_created_on_user_creation(self):
        (user,) = make_users(1)
        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(user.profile.total_games_played, 0)
