from unittest import mock

from django.test import TestCase

from game.game_engine import (
    GameEngine,
    GameFullError,
    GameNotJoinableError,
    InvalidMoveError,
    NotEnoughPlayersError,
    NotYourTurnError,
    card_point_value,
)
from game.models import Game, GameCard, MoveLog, PokemonCard
from game.tests.factories import make_cards, make_game, make_types, make_users


class GameEngineTestCase(TestCase):
    def setUp(self):
        self.types = make_types()
        self.cards = make_cards(self.types)
        self.users = make_users(3)
        self.game = make_game(self.users[0])
        self.engine = GameEngine(self.game)


class AddPlayerTests(GameEngineTestCase):
    def test_add_player_creates_gameplayer_with_incrementing_turn_order(self):
        p0 = self.engine.add_player(self.users[0])
        p1 = self.engine.add_player(self.users[1])
        self.assertEqual(p0.turn_order, 0)
        self.assertEqual(p1.turn_order, 1)

    def test_add_player_twice_returns_same_player(self):
        p0 = self.engine.add_player(self.users[0])
        p0_again = self.engine.add_player(self.users[0])
        self.assertEqual(p0.pk, p0_again.pk)
        self.assertEqual(self.game.players.count(), 1)

    def test_add_player_beyond_max_players_raises(self):
        self.game.max_players = 1
        self.game.save(update_fields=["max_players"])
        self.engine.add_player(self.users[0])
        with self.assertRaises(GameFullError):
            self.engine.add_player(self.users[1])


class StartGameTests(GameEngineTestCase):
    @mock.patch("game.game_engine.HAND_SIZE", 2)
    def test_start_game_requires_at_least_two_players(self):
        self.engine.add_player(self.users[0])
        with self.assertRaises(NotEnoughPlayersError):
            self.engine.start_game()

    @mock.patch("game.game_engine.HAND_SIZE", 2)
    def test_start_game_deals_correct_hand_sizes_and_sets_status(self):
        self.engine.add_player(self.users[0])
        self.engine.add_player(self.users[1])
        self.engine.start_game()

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.EN_COURS)

        for gp in self.game.players.all():
            hand_count = GameCard.objects.filter(
                game=self.game, location=GameCard.Location.MAIN, owner=gp
            ).count()
            self.assertEqual(hand_count, 2)

    @mock.patch("game.game_engine.HAND_SIZE", 2)
    def test_start_game_discard_top_is_never_legendary(self):
        self.engine.add_player(self.users[0])
        self.engine.add_player(self.users[1])
        self.engine.start_game()
        top = self.engine.get_top_discard()
        self.assertFalse(top.pokemon_card.is_legendary)

    @mock.patch("game.game_engine.HAND_SIZE", 2)
    def test_start_game_cannot_be_called_twice(self):
        self.engine.add_player(self.users[0])
        self.engine.add_player(self.users[1])
        self.engine.start_game()
        card_count = GameCard.objects.filter(game=self.game).count()

        with self.assertRaises(GameNotJoinableError):
            self.engine.start_game()

        self.assertEqual(GameCard.objects.filter(game=self.game).count(), card_count)

    def test_build_deck_uses_two_copies_of_each_active_catalogue_card(self):
        inactive_card = self.cards["charmander_evo"]
        inactive_card.in_current_deck = False
        inactive_card.save(update_fields=["in_current_deck"])

        self.engine.build_deck()
        from game.game_engine import DECK_COPIES_PER_CARD
        from game.models import PokemonCard

        active_cards = PokemonCard.objects.filter(in_current_deck=True)
        expected = active_cards.count() * DECK_COPIES_PER_CARD
        self.assertEqual(GameCard.objects.filter(game=self.game).count(), expected)
        for card in active_cards:
            self.assertEqual(
                GameCard.objects.filter(game=self.game, pokemon_card=card).count(),
                DECK_COPIES_PER_CARD,
            )
        self.assertFalse(GameCard.objects.filter(game=self.game, pokemon_card=inactive_card).exists())


class MoveValidationTests(GameEngineTestCase):
    @mock.patch("game.game_engine.HAND_SIZE", 2)
    def setUp(self):
        super().setUp()
        self.p0 = self.engine.add_player(self.users[0])
        self.p1 = self.engine.add_player(self.users[1])
        self.engine.start_game()
        self.current = self.engine.get_current_player()

    def _hand_of(self, player):
        return list(GameCard.objects.filter(game=self.game, location=GameCard.Location.MAIN, owner=player))

    def test_not_your_turn_raises(self):
        not_current = self.p1 if self.current.pk == self.p0.pk else self.p0
        card = self._hand_of(not_current)[0]
        with self.assertRaises(NotYourTurnError):
            self.engine.play_card(not_current, card)

    def test_card_not_in_hand_is_invalid(self):
        other_player = self.p1 if self.current.pk == self.p0.pk else self.p0
        foreign_card = self._hand_of(other_player)[0]
        ok, _ = self.engine.is_move_valid(self.current, foreign_card)
        self.assertFalse(ok)

    def test_legendary_card_always_playable(self):
        # On force une carte légendaire dans la main du joueur courant.
        legendary_instance = GameCard.objects.filter(
            game=self.game, pokemon_card=self.cards["zapdos"]
        ).first()
        legendary_instance.location = GameCard.Location.MAIN
        legendary_instance.owner = self.current
        legendary_instance.save(update_fields=["location", "owner"])

        ok, _ = self.engine.is_move_valid(self.current, legendary_instance)
        self.assertTrue(ok)

    def test_legendary_play_requires_declared_type(self):
        legendary_instance = GameCard.objects.filter(
            game=self.game, pokemon_card=self.cards["zapdos"]
        ).first()
        legendary_instance.location = GameCard.Location.MAIN
        legendary_instance.owner = self.current
        legendary_instance.save(update_fields=["location", "owner"])

        with self.assertRaises(InvalidMoveError):
            self.engine.play_card(self.current, legendary_instance, declared_type=None)


class PlayAndDrawTests(GameEngineTestCase):
    def setUp(self):
        super().setUp()
        self.p0 = self.engine.add_player(self.users[0])
        self.p1 = self.engine.add_player(self.users[1])

    def _force_hand(self, player, pokemon_cards):
        """Place des GameCard précises en main d'un joueur, pour un test déterministe."""
        cards = []
        for pc in pokemon_cards:
            gc = GameCard.objects.create(
                game=self.game,
                pokemon_card=pc,
                location=GameCard.Location.MAIN,
                owner=player,
                order_index=self.game.next_card_sequence(),
            )
            cards.append(gc)
        self.game.save(update_fields=["card_sequence_counter"])
        return cards

    def _set_discard_top(self, pokemon_card):
        gc = GameCard.objects.create(
            game=self.game,
            pokemon_card=pokemon_card,
            location=GameCard.Location.DEFAUSSE,
            order_index=self.game.next_card_sequence(),
        )
        self.game.save(update_fields=["card_sequence_counter"])
        return gc

    def _start_manually(self):
        self.game.status = Game.Status.EN_COURS
        self.game.current_turn_number = 0
        self.game.save(update_fields=["status", "current_turn_number"])

    def test_play_card_same_type_moves_to_discard_and_advances_turn(self):
        self._start_manually()
        current = self.engine.get_current_player()
        other = self.p1 if current.pk == self.p0.pk else self.p0

        self._set_discard_top(self.cards["charmander"])  # type Feu
        # Deux cartes en main : après en avoir joué une, la main n'est pas vide
        # (sinon la partie se termine au lieu de passer simplement au joueur suivant).
        hand = self._force_hand(current, [self.cards["charmander_evo"], self.cards["squirtle"]])

        self.engine.play_card(current, hand[0])

        hand[0].refresh_from_db()
        self.assertEqual(hand[0].location, GameCard.Location.DEFAUSSE)
        self.game.refresh_from_db()
        self.assertEqual(self.engine.get_current_player().pk, other.pk)

    def test_play_card_wrong_type_and_species_raises(self):
        self._start_manually()
        current = self.engine.get_current_player()

        self._set_discard_top(self.cards["charmander"])  # Feu
        hand = self._force_hand(current, [self.cards["squirtle"]])  # Eau, autre espèce

        with self.assertRaises(InvalidMoveError):
            self.engine.play_card(current, hand[0])

    def test_play_card_same_species_different_type_is_valid(self):
        self._start_manually()
        current = self.engine.get_current_player()

        self._set_discard_top(self.cards["charmander"])
        # Même pokedex_id que charmander (simulé) : on réutilise charmander lui-même.
        hand = self._force_hand(current, [self.cards["charmander"]])

        ok, _ = self.engine.is_move_valid(current, hand[0])
        self.assertTrue(ok)

    def test_draw_card_ends_turn_even_without_playing(self):
        self._start_manually()
        current = self.engine.get_current_player()
        other = self.p1 if current.pk == self.p0.pk else self.p0
        self.engine.build_deck()

        self.engine.draw_card(current)

        self.assertEqual(self.engine.get_current_player().pk, other.pk)
        self.assertTrue(
            GameCard.objects.filter(game=self.game, location=GameCard.Location.MAIN, owner=current).exists()
        )

    def test_draw_card_reshuffles_discard_when_pile_empty(self):
        self._start_manually()
        current = self.engine.get_current_player()

        # Une première carte en défausse : elle sera remélangée dans la pioche.
        GameCard.objects.create(
            game=self.game,
            pokemon_card=self.cards["squirtle"],
            location=GameCard.Location.DEFAUSSE,
            order_index=self.game.next_card_sequence(),
        )
        self.game.save(update_fields=["card_sequence_counter"])
        # Carte posée en dernier = dessus de la défausse (order_index le plus haut), doit rester en place.
        top = self._set_discard_top(self.cards["charmander"])

        self.engine.draw_card(current)

        # La carte du dessus de la défausse reste en défausse, l'autre a été remélangée.
        top.refresh_from_db()
        self.assertEqual(top.location, GameCard.Location.DEFAUSSE)
        self.assertTrue(
            GameCard.objects.filter(game=self.game, location=GameCard.Location.MAIN, owner=current).exists()
        )

    def test_advance_turn_wraps_around_to_first_player(self):
        self._start_manually()
        first = self.engine.get_current_player()
        self.engine.advance_turn()
        self.engine.advance_turn()
        self.assertEqual(self.engine.get_current_player().pk, first.pk)

    def test_end_game_scores_losers_by_remaining_hand_value(self):
        self._start_manually()
        current = self.engine.get_current_player()
        other = self.p1 if current.pk == self.p0.pk else self.p0

        self._force_hand(other, [self.cards["squirtle"], self.cards["zapdos"]])
        # Le gagnant vide sa main : dernière carte jouée.
        self._set_discard_top(self.cards["charmander"])
        winning_hand = self._force_hand(current, [self.cards["charmander_evo"]])

        self.engine.play_card(current, winning_hand[0])

        self.game.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.TERMINEE)
        # 10 (normale) + 25 (légendaire) = 35 points pour le perdant.
        self.assertEqual(other.score, 35)

    def test_end_game_updates_profile_stats(self):
        self._start_manually()
        current = self.engine.get_current_player()

        self._set_discard_top(self.cards["charmander"])
        winning_hand = self._force_hand(current, [self.cards["charmander_evo"]])
        self.engine.play_card(current, winning_hand[0])

        current.user.profile.refresh_from_db()
        self.assertEqual(current.user.profile.total_games_played, 1)
        self.assertEqual(current.user.profile.total_games_won, 1)


class ActionCardEffectsTests(GameEngineTestCase):
    def setUp(self):
        super().setUp()
        self.p0 = self.engine.add_player(self.users[0])
        self.p1 = self.engine.add_player(self.users[1])
        self.p2 = self.engine.add_player(self.users[2])
        self.game.status = Game.Status.EN_COURS
        self.game.current_turn_number = self.p0.turn_order
        self.game.save(update_fields=["status", "current_turn_number"])

    def _force_hand(self, player, pokemon_cards):
        cards = []
        for pokemon_card in pokemon_cards:
            cards.append(
                GameCard.objects.create(
                    game=self.game,
                    pokemon_card=pokemon_card,
                    location=GameCard.Location.MAIN,
                    owner=player,
                    order_index=self.game.next_card_sequence(),
                )
            )
        self.game.save(update_fields=["card_sequence_counter"])
        return cards

    def _set_discard_top(self, pokemon_card):
        card = GameCard.objects.create(
            game=self.game,
            pokemon_card=pokemon_card,
            location=GameCard.Location.DEFAUSSE,
            order_index=self.game.next_card_sequence(),
        )
        self.game.save(update_fields=["card_sequence_counter"])
        return card

    def _seed_draw_pile(self, count=8):
        for _ in range(count):
            GameCard.objects.create(
                game=self.game,
                pokemon_card=self.cards["bulbasaur"],
                location=GameCard.Location.PIOCHE,
                order_index=self.game.next_card_sequence(),
            )
        self.game.save(update_fields=["card_sequence_counter"])

    def _make_action(self, card_name, action):
        pokemon_card = self.cards[card_name]
        pokemon_card.action = action
        pokemon_card.save(update_fields=["action"])
        return pokemon_card

    def test_draw_two_makes_target_draw_and_skips_their_turn(self):
        draw_two = self._make_action("charmander", PokemonCard.Action.DRAW_TWO)
        self._set_discard_top(self.cards["charmander_evo"])
        hand = self._force_hand(self.p0, [draw_two, self.cards["squirtle"]])
        self._seed_draw_pile()

        self.engine.play_card(self.p0, hand[0])

        self.assertEqual(self.p1.hand_cards.count(), 2)
        self.assertEqual(self.engine.get_current_player().pk, self.p2.pk)
        self.assertTrue(
            MoveLog.objects.filter(
                game=self.game,
                player=self.p1,
                move_type=MoveLog.MoveType.PIOCHER,
            ).exists()
        )

    def test_draw_four_changes_type_draws_four_and_skips_target(self):
        draw_four = self._make_action("zapdos", PokemonCard.Action.DRAW_FOUR)
        self._set_discard_top(self.cards["charmander"])
        hand = self._force_hand(self.p0, [draw_four, self.cards["squirtle"]])
        self._seed_draw_pile()

        self.engine.play_card(self.p0, hand[0], declared_type=self.types["water"])

        self.game.refresh_from_db()
        self.assertEqual(self.game.active_type, self.types["water"])
        self.assertEqual(self.p1.hand_cards.count(), 4)
        self.assertEqual(self.engine.get_current_player().pk, self.p2.pk)

    def test_non_legendary_draw_four_requires_a_declared_type_in_state_contract(self):
        draw_four = self._make_action("charmander", PokemonCard.Action.DRAW_FOUR)
        self.assertFalse(draw_four.is_legendary)
        self._set_discard_top(self.cards["squirtle"])
        hand = self._force_hand(self.p0, [draw_four, self.cards["bulbasaur"]])

        state = self.engine.get_game_state(for_player=self.p0)
        own_state = next(player for player in state["players"] if player["id"] == self.p0.id)
        card_state = next(card for card in own_state["hand"] if card["id"] == hand[0].id)

        self.assertTrue(card_state["requires_declared_type"])
        with self.assertRaisesMessage(InvalidMoveError, "Cette carte impose de choisir le prochain type."):
            self.engine.play_card(self.p0, hand[0], declared_type=None)

    def test_reverse_changes_direction_before_selecting_next_player(self):
        reverse = self._make_action("charmander", PokemonCard.Action.REVERSE)
        self._set_discard_top(self.cards["charmander_evo"])
        hand = self._force_hand(self.p0, [reverse, self.cards["squirtle"]])

        self.engine.play_card(self.p0, hand[0])

        self.game.refresh_from_db()
        self.assertEqual(self.game.direction, -1)
        self.assertEqual(self.engine.get_current_player().pk, self.p2.pk)

    def test_shield_grants_protection_and_exposes_it_in_state(self):
        shield = self._make_action("charmander", PokemonCard.Action.SHIELD)
        self._set_discard_top(self.cards["charmander_evo"])
        hand = self._force_hand(self.p0, [shield, self.cards["squirtle"]])

        self.engine.play_card(self.p0, hand[0])

        self.p0.refresh_from_db()
        state = self.engine.get_game_state(for_player=self.p0)
        own_state = next(player for player in state["players"] if player["id"] == self.p0.id)
        self.assertTrue(self.p0.has_protection)
        self.assertTrue(own_state["has_protection"])
        self.assertEqual(state["top_discard"]["action"], PokemonCard.Action.SHIELD)
        self.assertEqual(state["top_discard"]["action_label"], "Protection")
        self.assertEqual(state["direction"], 1)

    def test_shield_cancels_penalty_is_consumed_and_preserves_target_turn(self):
        self.p1.has_protection = True
        self.p1.save(update_fields=["has_protection"])
        draw_two = self._make_action("charmander", PokemonCard.Action.DRAW_TWO)
        self._set_discard_top(self.cards["charmander_evo"])
        hand = self._force_hand(self.p0, [draw_two, self.cards["squirtle"]])
        self._seed_draw_pile()

        self.engine.play_card(self.p0, hand[0])

        self.p1.refresh_from_db()
        self.assertFalse(self.p1.has_protection)
        self.assertEqual(self.p1.hand_cards.count(), 0)
        self.assertEqual(self.engine.get_current_player().pk, self.p1.pk)


class CardPointValueTests(TestCase):
    def setUp(self):
        self.types = make_types()
        self.cards = make_cards(self.types)

    def test_normal_card_value(self):
        self.assertEqual(card_point_value(self.cards["charmander"]), 10)

    def test_legendary_card_value(self):
        self.assertEqual(card_point_value(self.cards["zapdos"]), 25)
