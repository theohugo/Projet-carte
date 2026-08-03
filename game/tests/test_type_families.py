from collections import Counter
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from game.deck_builder import count_cards_per_family
from game.game_engine import GameEngine
from game.models import Game, GameCard, PokemonCard
from game.type_families import (
    FAMILY_BY_SLUG,
    TYPE_FAMILIES,
    family_slugs_for_card,
    family_slugs_for_types,
)

EXPECTED_TYPE_SLUGS = {
    "bug",
    "dark",
    "dragon",
    "electric",
    "fairy",
    "fighting",
    "fire",
    "flying",
    "ghost",
    "grass",
    "ground",
    "ice",
    "normal",
    "poison",
    "psychic",
    "rock",
    "steel",
    "water",
}

EXPECTED_CATALOGUE_COUNTS = {
    "ecosystem": 9,
    "shadows": 8,
    "forge": 9,
    "arcane": 8,
    "tides": 8,
    "skyfire": 8,
    "instinct": 9,
    "storm": 8,
}


class TypeFamilyDefinitionTests(SimpleTestCase):
    def test_exactly_eight_families_assign_every_type_once(self):
        assigned_types = [type_slug for family in TYPE_FAMILIES for type_slug in family.type_slugs]

        self.assertEqual(len(TYPE_FAMILIES), 8)
        self.assertEqual(len(FAMILY_BY_SLUG), 8)
        self.assertEqual(Counter(assigned_types), Counter({slug: 1 for slug in EXPECTED_TYPE_SLUGS}))

    def test_types_from_the_same_family_are_deduplicated(self):
        self.assertEqual(
            family_slugs_for_types(("bug", "grass", "poison", "grass")),
            ("ecosystem",),
        )


class TypeFamilyFixtureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_pokemon_cards", stdout=StringIO())
        cls.cards = list(
            PokemonCard.objects.filter(in_current_deck=True).select_related("primary_type", "secondary_type")
        )

    def test_fixture_and_two_copy_deck_stay_between_expected_family_bounds(self):
        catalogue_counts = count_cards_per_family(self.cards)
        two_copy_pool = [card for card in self.cards for _ in range(2)]
        deck_counts = count_cards_per_family(two_copy_pool)

        self.assertEqual(len(self.cards), 54)
        self.assertEqual(catalogue_counts, Counter(EXPECTED_CATALOGUE_COUNTS))
        self.assertEqual((min(catalogue_counts.values()), max(catalogue_counts.values())), (8, 9))
        self.assertEqual(
            deck_counts,
            Counter({slug: count * 2 for slug, count in EXPECTED_CATALOGUE_COUNTS.items()}),
        )
        self.assertEqual((min(deck_counts.values()), max(deck_counts.values())), (16, 18))

    def test_every_serialized_card_exposes_one_or_two_valid_families(self):
        user = get_user_model().objects.create_user(username="family-tester", password="pass12345")
        game = Game.objects.create(created_by=user)
        engine = GameEngine(game)
        player = engine.add_player(user)
        expected_families_by_instance = {}

        for order_index, pokemon_card in enumerate(self.cards, start=1):
            game_card = GameCard.objects.create(
                game=game,
                pokemon_card=pokemon_card,
                location=GameCard.Location.MAIN,
                owner=player,
                order_index=order_index,
            )
            expected_families_by_instance[game_card.pk] = list(family_slugs_for_card(pokemon_card))

        state = engine.get_game_state(for_player=player)
        serialized_player = next(entry for entry in state["players"] if entry["id"] == player.pk)
        serialized_cards = serialized_player["hand"]
        valid_family_slugs = set(FAMILY_BY_SLUG)

        self.assertEqual(len(serialized_cards), 54)
        for serialized_card in serialized_cards:
            families = serialized_card["families"]
            self.assertIn(len(families), (1, 2))
            self.assertEqual(len(families), len(set(families)))
            self.assertTrue(set(families) <= valid_family_slugs)
            self.assertEqual(families, expected_families_by_instance[serialized_card["id"]])
