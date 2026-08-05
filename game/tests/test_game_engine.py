from collections import Counter
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
from game.tests.factories import make_cards, make_draft_catalogue, make_game, make_types, make_users


class GameEngineTestCase(TestCase):
    def setUp(self):
        self.types = make_types()
        self.cards = make_cards(self.types)
        # Le tirage exige quatre types assez fournis : sans ce catalogue,
        # `start_game` échouerait avant même de distribuer les cartes.
        make_draft_catalogue(self.types)
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

    def test_build_deck_draws_four_types_and_two_copies_of_each_species(self):
        from game.game_engine import DECK_COPIES_PER_CARD
        from game.pokemon_types import GAME_TYPE_COUNT, SPECIES_PER_TYPE

        selected_types = self.engine.build_deck()

        self.assertEqual(len(selected_types), GAME_TYPE_COUNT)
        self.assertEqual(self.game.selected_types.count(), GAME_TYPE_COUNT)

        deck = GameCard.objects.filter(game=self.game).select_related(
            "pokemon_card__primary_type", "pokemon_card__secondary_type"
        )
        copies = Counter(game_card.pokemon_card_id for game_card in deck)
        self.assertEqual(set(copies.values()), {DECK_COPIES_PER_CARD})

        species_per_type = Counter()
        for pokemon_card_id in copies:
            card = next(gc.pokemon_card for gc in deck if gc.pokemon_card_id == pokemon_card_id)
            for pokemon_type in card.types:
                species_per_type[pokemon_type.slug] += 1
        for pokemon_type in selected_types:
            self.assertGreaterEqual(species_per_type[pokemon_type.slug], SPECIES_PER_TYPE)

    def test_build_deck_ignores_species_excluded_from_the_catalogue(self):
        excluded = self.cards["charmander_evo"]
        excluded.in_current_deck = False
        excluded.save(update_fields=["in_current_deck"])

        self.engine.build_deck()

        self.assertFalse(GameCard.objects.filter(game=self.game, pokemon_card=excluded).exists())

    def test_build_deck_gives_the_deck_its_share_of_action_cards(self):
        self.engine.build_deck()

        deck = list(GameCard.objects.filter(game=self.game))
        with_action = [card for card in deck if card.action != GameCard.Action.NORMAL]

        self.assertGreater(len(with_action), 0)
        # Une espèce garde le même pouvoir sur ses deux exemplaires.
        actions_by_species = {}
        for card in deck:
            actions_by_species.setdefault(card.pokemon_card_id, set()).add(card.action)
        self.assertTrue(all(len(actions) == 1 for actions in actions_by_species.values()))


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

    def _put_card(self, pokemon_card, *, location, owner=None):
        card = GameCard.objects.create(
            game=self.game,
            pokemon_card=pokemon_card,
            location=location,
            owner=owner,
            order_index=self.game.next_card_sequence(),
        )
        self.game.save(update_fields=["card_sequence_counter"])
        return card

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

    def test_a_shared_type_makes_the_card_playable(self):
        self._put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        candidate = self._put_card(
            self.cards["charmander_evo"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )

        ok, reason = self.engine.is_move_valid(self.current, candidate)

        self.assertTrue(ok, reason)

    def test_a_secondary_type_is_enough_to_bridge_two_cards(self):
        # Bulbizarre est Plante/Poison : son second type suffit à l'enchaîner
        # sur une carte Poison, même sans partager le type principal.
        nidoran = PokemonCard.objects.create(
            pokedex_id=29,
            slug="nidoran-f",
            name_fr="Nidoran♀",
            name_en="Nidoran-F",
            primary_type=self.types["poison"],
            sprite_url="https://example.com/29.png",
        )
        self._put_card(nidoran, location=GameCard.Location.DEFAUSSE)
        candidate = self._put_card(
            self.cards["bulbasaur"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )

        ok, reason = self.engine.is_move_valid(self.current, candidate)

        self.assertTrue(ok, reason)

    def test_no_shared_type_and_another_species_is_refused(self):
        self._put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        candidate = self._put_card(
            self.cards["squirtle"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )

        ok, reason = self.engine.is_move_valid(self.current, candidate)

        self.assertFalse(ok)
        self.assertIn("aucun type", reason)

    def test_active_type_overrides_the_top_card_type(self):
        self._put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        water_candidate = self._put_card(
            self.cards["squirtle"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )
        grass_candidate = self._put_card(
            self.cards["bulbasaur"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )
        self.game.active_type = self.types["water"]
        self.game.save(update_fields=["active_type"])

        water_ok, water_reason = self.engine.is_move_valid(self.current, water_candidate)
        grass_ok, _ = self.engine.is_move_valid(self.current, grass_candidate)

        self.assertTrue(water_ok, water_reason)
        self.assertFalse(grass_ok)

    def test_normal_card_clears_a_previously_imposed_type(self):
        self.game.active_type = self.types["fire"]
        self.game.save(update_fields=["active_type"])
        self._put_card(self.cards["charmander"], location=GameCard.Location.DEFAUSSE)
        candidate = self._put_card(
            self.cards["charmander_evo"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )

        self.engine.play_card(self.current, candidate, declared_type_slug="grass")

        self.game.refresh_from_db()
        move = MoveLog.objects.get(game=self.game, game_card=candidate)
        self.assertIsNone(self.game.active_type)
        self.assertIsNone(move.declared_type)

    def test_legendary_card_always_playable(self):
        # On force une carte légendaire dans la main du joueur courant.
        legendary_instance = GameCard.objects.filter(
            game=self.game, pokemon_card=self.cards["zapdos"]
        ).first() or self._put_card(
            self.cards["zapdos"],
            location=GameCard.Location.PIOCHE,
        )
        legendary_instance.location = GameCard.Location.MAIN
        legendary_instance.owner = self.current
        legendary_instance.save(update_fields=["location", "owner"])

        ok, _ = self.engine.is_move_valid(self.current, legendary_instance)
        self.assertTrue(ok)

    def test_legendary_play_requires_a_type_drawn_for_this_game(self):
        legendary_instance = self._put_card(
            self.cards["zapdos"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )

        with self.assertRaises(InvalidMoveError):
            self.engine.play_card(self.current, legendary_instance, declared_type_slug=None)

        # Le Poison n'a pas été tiré pour cette partie : il ne peut pas être imposé.
        with self.assertRaises(InvalidMoveError):
            self.engine.play_card(self.current, legendary_instance, declared_type_slug="poison")

    def test_legendary_play_imposes_the_declared_type(self):
        legendary_instance = self._put_card(
            self.cards["zapdos"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )
        declared = self.engine.get_selected_types().first()

        self.engine.play_card(self.current, legendary_instance, declared_type_slug=declared.slug)

        self.game.refresh_from_db()
        move = MoveLog.objects.get(game=self.game, game_card=legendary_instance)
        self.assertEqual(self.game.active_type, declared)
        self.assertEqual(move.declared_type, declared)

    def test_state_exposes_the_game_types_and_card_types(self):
        legendary_instance = self._put_card(
            self.cards["zapdos"],
            location=GameCard.Location.MAIN,
            owner=self.current,
        )

        state = self.engine.get_game_state(for_player=self.current)
        own_state = next(player for player in state["players"] if player["id"] == self.current.id)
        card_state = next(card for card in own_state["hand"] if card["id"] == legendary_instance.id)

        self.assertEqual(len(state["game_types"]), 4)
        self.assertEqual(
            {entry["slug"] for entry in state["game_types"]},
            set(self.engine.get_selected_types().values_list("slug", flat=True)),
        )
        self.assertTrue(all(entry["color"].startswith("#") for entry in state["game_types"]))
        self.assertIsNone(state["active_type"])
        self.assertEqual([entry["slug"] for entry in card_state["types"]], ["flying"])
        self.assertTrue(card_state["requires_type_choice"])
        for legacy_key in ("active_tcg_type", "available_tcg_types"):
            self.assertNotIn(legacy_key, state)
        for legacy_key in ("tcg_type", "tcg_type_label", "requires_tcg_type_choice"):
            self.assertNotIn(legacy_key, card_state)


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

    def test_end_game_awards_remaining_hand_value_to_winner(self):
        self._start_manually()
        current = self.engine.get_current_player()
        other = self.p1 if current.pk == self.p0.pk else self.p0

        self._force_hand(other, [self.cards["squirtle"], self.cards["zapdos"]])
        # Le gagnant vide sa main : dernière carte jouée.
        self._set_discard_top(self.cards["charmander"])
        winning_hand = self._force_hand(current, [self.cards["charmander_evo"]])

        self.engine.play_card(current, winning_hand[0])

        self.game.refresh_from_db()
        current.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.TERMINEE)
        # 10 (normale) + 25 (légendaire) = 35 points pour le gagnant.
        self.assertEqual(current.score, 35)
        self.assertEqual(other.score, 0)

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

    def _make_action(self, game_card, action):
        """Attribue un pouvoir à une carte physique déjà en jeu."""
        game_card.action = action
        game_card.save(update_fields=["action"])
        return game_card

    def _give_game_types(self, *slugs):
        self.game.selected_types.set([self.types[slug] for slug in slugs])

    def test_draw_two_makes_target_draw_and_skips_their_turn(self):
        self._set_discard_top(self.cards["charmander_evo"])
        hand = self._force_hand(self.p0, [self.cards["charmander"], self.cards["squirtle"]])
        self._make_action(hand[0], GameCard.Action.DRAW_TWO)
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

    def test_draw_four_imposes_a_type_draws_four_and_skips_target(self):
        self._give_game_types("fire", "water", "grass", "flying")
        self._set_discard_top(self.cards["charmander"])
        hand = self._force_hand(self.p0, [self.cards["zapdos"], self.cards["squirtle"]])
        self._make_action(hand[0], GameCard.Action.DRAW_FOUR)
        self._seed_draw_pile()

        self.engine.play_card(self.p0, hand[0], declared_type_slug="water")

        self.game.refresh_from_db()
        move = MoveLog.objects.get(game=self.game, game_card=hand[0])
        self.assertEqual(self.game.active_type, self.types["water"])
        self.assertEqual(move.declared_type, self.types["water"])
        self.assertEqual(self.p1.hand_cards.count(), 4)
        self.assertEqual(self.engine.get_current_player().pk, self.p2.pk)

    def test_non_legendary_draw_four_requires_a_type_in_state_contract(self):
        self._give_game_types("fire", "water", "grass", "flying")
        self._set_discard_top(self.cards["squirtle"])
        hand = self._force_hand(self.p0, [self.cards["charmander"], self.cards["bulbasaur"]])
        self._make_action(hand[0], GameCard.Action.DRAW_FOUR)
        self.assertFalse(hand[0].pokemon_card.is_legendary)

        state = self.engine.get_game_state(for_player=self.p0)
        own_state = next(player for player in state["players"] if player["id"] == self.p0.id)
        card_state = next(card for card in own_state["hand"] if card["id"] == hand[0].id)

        self.assertTrue(card_state["requires_type_choice"])
        with self.assertRaisesMessage(
            InvalidMoveError,
            "Cette carte impose de choisir un des types de la partie.",
        ):
            self.engine.play_card(self.p0, hand[0], declared_type_slug=None)

    def test_reverse_changes_direction_before_selecting_next_player(self):
        self._set_discard_top(self.cards["charmander_evo"])
        hand = self._force_hand(self.p0, [self.cards["charmander"], self.cards["squirtle"]])
        self._make_action(hand[0], GameCard.Action.REVERSE)

        self.engine.play_card(self.p0, hand[0])

        self.game.refresh_from_db()
        self.assertEqual(self.game.direction, -1)
        self.assertEqual(self.engine.get_current_player().pk, self.p2.pk)

    def test_shield_grants_protection_and_exposes_it_in_state(self):
        self._set_discard_top(self.cards["charmander_evo"])
        hand = self._force_hand(self.p0, [self.cards["charmander"], self.cards["squirtle"]])
        self._make_action(hand[0], GameCard.Action.SHIELD)

        self.engine.play_card(self.p0, hand[0])

        self.p0.refresh_from_db()
        state = self.engine.get_game_state(for_player=self.p0)
        own_state = next(player for player in state["players"] if player["id"] == self.p0.id)
        self.assertTrue(self.p0.has_protection)
        self.assertTrue(own_state["has_protection"])
        self.assertEqual(state["top_discard"]["action"], GameCard.Action.SHIELD)
        self.assertEqual(state["top_discard"]["action_label"], "Protection")
        self.assertEqual(state["direction"], 1)

    def test_shield_cancels_penalty_is_consumed_and_preserves_target_turn(self):
        self.p1.has_protection = True
        self.p1.save(update_fields=["has_protection"])
        self._set_discard_top(self.cards["charmander_evo"])
        hand = self._force_hand(self.p0, [self.cards["charmander"], self.cards["squirtle"]])
        self._make_action(hand[0], GameCard.Action.DRAW_TWO)
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
