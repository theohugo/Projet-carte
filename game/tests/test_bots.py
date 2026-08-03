import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from game.bot_player import perform_bot_turn
from game.game_engine import GameEngine
from game.models import Game, GameCard, MoveLog, PokemonCard, Profile
from game.tests.factories import make_cards, make_game, make_types, make_users

User = get_user_model()


class BotGameTestCase(TestCase):
    def setUp(self):
        self.types = make_types()
        self.cards = make_cards(self.types)
        self.host, self.other_user = make_users(2)
        self.game = make_game(self.host)
        self.engine = GameEngine(self.game)
        self.human = self.engine.add_player(self.host)
        self.bot = self.engine.add_bot()

    def set_running(self, *, current_player=None, turn_revision=1):
        current_player = current_player or self.bot
        self.game.status = Game.Status.EN_COURS
        self.game.current_turn_number = current_player.turn_order
        self.game.turn_revision = turn_revision
        self.game.save(update_fields=["status", "current_turn_number", "turn_revision"])

    def put_card(self, pokemon_card, *, location, owner=None):
        card = GameCard.objects.create(
            game=self.game,
            pokemon_card=pokemon_card,
            location=location,
            owner=owner,
            order_index=self.game.next_card_sequence(),
        )
        self.game.save(update_fields=["card_sequence_counter"])
        return card


class BotLobbyTests(BotGameTestCase):
    def test_add_bot_does_not_create_user_and_remove_compacts_turn_order(self):
        user_count = User.objects.count()
        human_after_bot = self.engine.add_player(self.other_user)
        second_bot = self.engine.add_bot()

        self.assertEqual(User.objects.count(), user_count)
        self.assertTrue(self.bot.is_bot)
        self.assertIsNone(self.bot.user_id)
        self.assertTrue(self.bot.display_name.startswith("IA "))
        self.assertEqual(
            [self.human.turn_order, self.bot.turn_order, human_after_bot.turn_order, second_bot.turn_order],
            [0, 1, 2, 3],
        )

        self.engine.remove_bot(self.bot.id)
        human_after_bot.refresh_from_db()
        second_bot.refresh_from_db()

        self.assertFalse(self.game.players.filter(pk=self.bot.id).exists())
        self.assertEqual(human_after_bot.turn_order, 1)
        self.assertEqual(second_bot.turn_order, 2)
        self.assertEqual(
            list(self.game.players.order_by("turn_order").values_list("turn_order", flat=True)),
            [0, 1, 2],
        )


class BotDecisionTests(BotGameTestCase):
    def test_bot_plays_a_valid_card(self):
        self.set_running()
        self.put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        playable = self.put_card(
            self.cards["charmander_evo"], location=GameCard.Location.MAIN, owner=self.bot
        )
        unplayable = self.put_card(self.cards["squirtle"], location=GameCard.Location.MAIN, owner=self.bot)

        decision = perform_bot_turn(self.engine)

        playable.refresh_from_db()
        unplayable.refresh_from_db()
        self.game.refresh_from_db()
        self.assertEqual(decision.kind, "play")
        self.assertEqual(decision.card_id, playable.id)
        self.assertEqual(playable.location, GameCard.Location.DEFAUSSE)
        self.assertIsNone(playable.owner_id)
        self.assertEqual(unplayable.location, GameCard.Location.MAIN)
        self.assertEqual(self.game.current_turn_number, self.human.turn_order)
        self.assertEqual(self.game.turn_revision, 2)

    def test_bot_draws_when_no_card_is_playable(self):
        self.set_running()
        self.put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        self.put_card(self.cards["squirtle"], location=GameCard.Location.MAIN, owner=self.bot)
        drawn = self.put_card(self.cards["bulbasaur"], location=GameCard.Location.PIOCHE)

        decision = perform_bot_turn(self.engine)

        drawn.refresh_from_db()
        self.game.refresh_from_db()
        self.assertEqual(decision.kind, "draw")
        self.assertEqual(drawn.location, GameCard.Location.MAIN)
        self.assertEqual(drawn.owner_id, self.bot.id)
        self.assertEqual(self.bot.hand_cards.count(), 2)
        self.assertEqual(self.game.current_turn_number, self.human.turn_order)
        self.assertEqual(self.game.turn_revision, 2)

    def test_wild_card_declares_the_most_common_remaining_family(self):
        self.set_running()
        self.put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        wild = self.put_card(self.cards["zapdos"], location=GameCard.Location.MAIN, owner=self.bot)
        self.put_card(self.cards["bulbasaur"], location=GameCard.Location.MAIN, owner=self.bot)
        self.put_card(self.cards["bulbasaur"], location=GameCard.Location.MAIN, owner=self.bot)
        self.put_card(self.cards["squirtle"], location=GameCard.Location.MAIN, owner=self.bot)

        decision = perform_bot_turn(self.engine)

        wild.refresh_from_db()
        self.game.refresh_from_db()
        move = MoveLog.objects.get(
            game=self.game,
            player=self.bot,
            move_type=MoveLog.MoveType.JOUER_CARTE,
        )
        self.assertEqual(decision.kind, "play")
        self.assertEqual(decision.card_id, wild.id)
        self.assertEqual(decision.declared_family, "ecosystem")
        self.assertEqual(self.game.active_family, "ecosystem")
        self.assertEqual(move.declared_family, "ecosystem")

    def test_bot_can_win_without_creating_a_profile(self):
        self.set_running()
        self.put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        self.put_card(self.cards["charmander_evo"], location=GameCard.Location.MAIN, owner=self.bot)
        self.put_card(self.cards["squirtle"], location=GameCard.Location.MAIN, owner=self.human)
        profile_count = Profile.objects.count()
        user_count = User.objects.count()

        perform_bot_turn(self.engine)

        self.game.refresh_from_db()
        self.host.profile.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.TERMINEE)
        self.assertEqual(Profile.objects.count(), profile_count)
        self.assertEqual(User.objects.count(), user_count)
        self.assertEqual(self.host.profile.total_games_played, 1)
        self.assertEqual(self.host.profile.total_games_won, 0)
        self.assertTrue(
            MoveLog.objects.filter(
                game=self.game,
                player=self.bot,
                move_type=MoveLog.MoveType.FIN_PARTIE,
            ).exists()
        )


class BotApiTests(BotGameTestCase):
    def test_bot_turn_endpoint_is_idempotent_for_a_stale_revision(self):
        self.set_running(turn_revision=9)
        draw_two = self.cards["charmander"]
        draw_two.action = PokemonCard.Action.DRAW_TWO
        draw_two.save(update_fields=["action"])
        self.put_card(self.cards["charmander_evo"], location=GameCard.Location.DEFAUSSE)
        played_card = self.put_card(draw_two, location=GameCard.Location.MAIN, owner=self.bot)
        private_card = self.put_card(
            self.cards["charmander_evo"], location=GameCard.Location.MAIN, owner=self.bot
        )
        self.put_card(self.cards["bulbasaur"], location=GameCard.Location.PIOCHE)
        self.put_card(self.cards["bulbasaur"], location=GameCard.Location.PIOCHE)
        self.client.force_login(self.host)
        url = reverse("api_bot_turn", args=[self.game.id])
        payload = json.dumps({"expected_turn_revision": 9})

        first = self.client.post(url, data=payload, content_type="application/json")
        second = self.client.post(url, data=payload, content_type="application/json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.game.refresh_from_db()
        played_card.refresh_from_db()
        private_card.refresh_from_db()
        self.assertEqual(self.game.turn_revision, 10)
        self.assertEqual(self.game.current_turn_number, self.bot.turn_order)
        self.assertEqual(played_card.location, GameCard.Location.DEFAUSSE)
        self.assertEqual(private_card.location, GameCard.Location.MAIN)
        self.assertEqual(
            MoveLog.objects.filter(
                game=self.game,
                player=self.bot,
                move_type=MoveLog.MoveType.JOUER_CARTE,
            ).count(),
            1,
        )
        self.assertEqual(first.json()["turn_revision"], 10)
        self.assertEqual(second.json()["turn_revision"], 10)

    def test_bot_hand_state_exposes_only_public_metadata_and_count(self):
        self.set_running(turn_revision=4)
        self.put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        private_card = self.put_card(self.cards["squirtle"], location=GameCard.Location.MAIN, owner=self.bot)
        self.client.force_login(self.host)

        response = self.client.get(reverse("api_game_state", args=[self.game.id]))

        self.assertEqual(response.status_code, 200)
        state = response.json()
        bot_state = next(player for player in state["players"] if player["id"] == self.bot.id)
        self.assertEqual(
            set(bot_state),
            {
                "id",
                "username",
                "is_bot",
                "turn_order",
                "score",
                "has_protection",
                "is_current_turn",
                "hand_count",
            },
        )
        self.assertTrue(bot_state["is_bot"])
        self.assertEqual(bot_state["hand_count"], 1)
        serialized = json.dumps(state, ensure_ascii=False)
        self.assertNotIn(private_card.pokemon_card.name_fr, serialized)
        self.assertNotIn(private_card.pokemon_card.sprite_url, serialized)
