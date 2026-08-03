from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from game.game_engine import (
    TURN_INACTIVITY_TIMEOUT,
    WAITING_ROOM_TIMEOUT,
    GameEngine,
    close_stale_games,
)
from game.models import Game, MoveLog
from game.tests.factories import make_cards, make_game, make_types, make_users


class CloseStaleGamesTests(TestCase):
    def setUp(self):
        make_cards(make_types())
        self.users = make_users(2)
        self.game = make_game(self.users[0])
        self.engine = GameEngine(self.game)
        self.engine.add_player(self.users[0])
        self.engine.add_player(self.users[1])

    def _start_manually(self):
        """Passe la partie EN_COURS sans distribuer de vraies mains : le
        fixture de test n'a que 5 cartes, insuffisant pour un deal complet.
        close_stale_games() ne regarde que le statut et l'horodatage des
        MoveLog, donc un DEBUT_PARTIE simulé suffit."""
        self.game.status = Game.Status.EN_COURS
        self.game.save(update_fields=["status"])
        MoveLog.objects.create(game=self.game, move_type=MoveLog.MoveType.DEBUT_PARTIE)

    def _age_waiting_room(self, delta):
        Game.objects.filter(pk=self.game.pk).update(created_at=timezone.now() - delta)

    def _age_last_activity(self, delta):
        MoveLog.objects.filter(game=self.game).update(created_at=timezone.now() - delta)

    def test_waiting_room_under_the_timeout_is_left_open(self):
        self._age_waiting_room(WAITING_ROOM_TIMEOUT - timedelta(minutes=1))

        close_stale_games()

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.EN_ATTENTE)
        self.assertIsNone(self.game.finished_at)

    def test_waiting_room_past_the_timeout_is_closed(self):
        self._age_waiting_room(WAITING_ROOM_TIMEOUT + timedelta(minutes=1))

        close_stale_games()

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.TERMINEE)
        self.assertIsNotNone(self.game.finished_at)

    def test_active_game_with_recent_move_is_left_running(self):
        self._start_manually()
        self._age_last_activity(TURN_INACTIVITY_TIMEOUT - timedelta(minutes=1))

        close_stale_games()

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.EN_COURS)
        self.assertIsNone(self.game.finished_at)

    def test_active_game_without_a_move_past_the_timeout_is_closed(self):
        self._start_manually()
        self._age_last_activity(TURN_INACTIVITY_TIMEOUT + timedelta(minutes=1))

        close_stale_games()

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.TERMINEE)
        self.assertIsNotNone(self.game.finished_at)
        self.assertTrue(MoveLog.objects.filter(game=self.game, move_type=MoveLog.MoveType.ABANDON).exists())

    def test_already_finished_game_is_left_alone(self):
        self._start_manually()
        self._age_last_activity(TURN_INACTIVITY_TIMEOUT + timedelta(minutes=1))
        self.game.status = Game.Status.TERMINEE
        self.game.save(update_fields=["status"])

        close_stale_games()

        self.assertFalse(MoveLog.objects.filter(game=self.game, move_type=MoveLog.MoveType.ABANDON).exists())
