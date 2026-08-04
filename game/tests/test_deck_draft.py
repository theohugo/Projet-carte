"""Tirage de la pioche : types de la partie, espèces retenues et pouvoirs."""

import random
from collections import Counter

from django.test import TestCase

from game.card_actions import ACTION_SHARES, assign_actions
from game.deck_builder import DeckDraftError, draw_game_types, select_species, species_by_type
from game.models import GameCard, PokemonCard
from game.pokemon_types import GAME_TYPE_COUNT, SPECIES_PER_TYPE
from game.tests.factories import make_cards, make_draft_catalogue, make_types


class DeckDraftTests(TestCase):
    def setUp(self):
        self.types = make_types()
        self.cards = make_cards(self.types)
        make_draft_catalogue(self.types)
        self.catalogue = list(PokemonCard.objects.select_related("primary_type", "secondary_type"))

    def test_draws_the_requested_number_of_distinct_types(self):
        drawn = draw_game_types(self.catalogue, random.Random(1))

        self.assertEqual(len(drawn), GAME_TYPE_COUNT)
        self.assertEqual(len(set(drawn)), GAME_TYPE_COUNT)

    def test_only_types_with_enough_species_can_be_drawn(self):
        # Le Poison n'est porté que par Bulbizarre : il ne peut pas être tiré.
        drawn = draw_game_types(self.catalogue, random.Random(7))

        self.assertNotIn("poison", drawn)

    def test_a_catalogue_too_thin_refuses_the_draw(self):
        with self.assertRaises(DeckDraftError):
            draw_game_types(self.catalogue, random.Random(1), species_per_type=SPECIES_PER_TYPE * 10)

    def test_each_drawn_type_gets_its_share_of_species(self):
        drawn = draw_game_types(self.catalogue, random.Random(3))

        species = select_species(self.catalogue, drawn, random.Random(3))

        pools = species_by_type(species)
        for slug in drawn:
            self.assertGreaterEqual(len(pools[slug]), SPECIES_PER_TYPE)

    def test_a_species_is_never_selected_twice(self):
        drawn = draw_game_types(self.catalogue, random.Random(5))

        species = select_species(self.catalogue, drawn, random.Random(5))

        self.assertEqual(len(species), len({card.pk for card in species}))

    def test_the_draw_changes_from_one_game_to_the_next(self):
        draws = {tuple(sorted(draw_game_types(self.catalogue, random.Random(seed)))) for seed in range(20)}

        # Quatre types éligibles seulement dans ce catalogue de test : le tirage
        # est stable, mais les espèces retenues, elles, doivent varier.
        selections = {
            frozenset(
                card.pk
                for card in select_species(
                    self.catalogue,
                    draw_game_types(self.catalogue, random.Random(seed)),
                    random.Random(seed),
                )
            )
            for seed in range(20)
        }
        self.assertGreaterEqual(len(draws), 1)
        self.assertGreater(len(selections), 1)


class ActionQuotaTests(TestCase):
    def setUp(self):
        self.types = make_types()
        self.cards = make_cards(self.types)
        self.species = make_draft_catalogue(self.types)

    def test_each_action_gets_its_share_of_the_drawn_species(self):
        actions = assign_actions(self.species, random.Random(11))

        counts = Counter(actions.values())
        for action, share in ACTION_SHARES:
            self.assertEqual(counts[action], round(len(self.species) * share))

    def test_legendary_species_never_receive_an_action(self):
        species = [*self.species, self.cards["zapdos"]]

        actions = assign_actions(species, random.Random(13))

        self.assertNotIn(self.cards["zapdos"].pk, actions)

    def test_species_without_an_action_stay_normal(self):
        actions = assign_actions(self.species, random.Random(17))

        normal = [card for card in self.species if card.pk not in actions]
        self.assertGreater(len(normal), 0)
        self.assertEqual(
            {actions.get(card.pk, GameCard.Action.NORMAL) for card in normal},
            {GameCard.Action.NORMAL},
        )
