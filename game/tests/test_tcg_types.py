from collections import Counter
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from game.deck_builder import count_cards_per_tcg_type
from game.game_engine import GameEngine
from game.models import Game, GameCard, PokemonCard
from game.tcg_types import (
    POKEMON_TYPE_TO_TCG_TYPE,
    TCG_TYPE_BY_SLUG,
    TCG_TYPES,
    get_tcg_type,
)

EXPECTED_SOURCE_TYPE_SLUGS = {
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

EXPECTED_TCG_TYPE_SLUGS = {
    "fire",
    "grass",
    "lightning",
    "water",
}

EXPECTED_CATALOGUE_COUNTS = {
    "fire": 5,
    "grass": 6,
    "lightning": 5,
    "water": 6,
}


class TcgTypeDefinitionTests(SimpleTestCase):
    def test_exactly_four_tcg_types_have_unique_slugs(self):
        slugs = [tcg_type.slug for tcg_type in TCG_TYPES]

        self.assertEqual(len(TCG_TYPES), 4)
        self.assertEqual(len(TCG_TYPE_BY_SLUG), 4)
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertEqual(set(slugs), EXPECTED_TCG_TYPE_SLUGS)

    def test_source_mapping_covers_all_eighteen_pokemon_types(self):
        self.assertEqual(set(POKEMON_TYPE_TO_TCG_TYPE), EXPECTED_SOURCE_TYPE_SLUGS)
        self.assertTrue(set(POKEMON_TYPE_TO_TCG_TYPE.values()) <= EXPECTED_TCG_TYPE_SLUGS)

    def test_tcg_type_lookup_rejects_legacy_or_unknown_slugs(self):
        self.assertEqual(get_tcg_type(" Lightning ").slug, "lightning")
        self.assertIsNone(get_tcg_type("storm"))
        self.assertIsNone(get_tcg_type("electric"))
        self.assertIsNone(get_tcg_type(None))


class TcgTypeFixtureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_pokemon_cards", stdout=StringIO())
        cls.cards = list(
            PokemonCard.objects.filter(in_current_deck=True).select_related(
                "primary_type",
                "secondary_type",
            )
        )

    def test_fixture_and_two_copy_deck_have_expected_tcg_balance(self):
        catalogue_counts = count_cards_per_tcg_type(self.cards)
        two_copy_pool = [card for card in self.cards for _ in range(2)]
        deck_counts = count_cards_per_tcg_type(two_copy_pool)

        self.assertEqual(len(self.cards), 22)
        self.assertEqual(catalogue_counts, Counter(EXPECTED_CATALOGUE_COUNTS))
        self.assertEqual(
            (min(catalogue_counts.values()), max(catalogue_counts.values())),
            (5, 6),
        )
        self.assertEqual(
            deck_counts,
            Counter({slug: count * 2 for slug, count in EXPECTED_CATALOGUE_COUNTS.items()}),
        )
        self.assertEqual((min(deck_counts.values()), max(deck_counts.values())), (10, 12))

    def test_every_catalogue_card_has_one_valid_tcg_type(self):
        for card in self.cards:
            with self.subTest(card=card.slug):
                self.assertIsInstance(card.tcg_type, str)
                self.assertIn(card.tcg_type, TCG_TYPE_BY_SLUG)

    def test_serialized_cards_expose_only_the_tcg_gameplay_contract(self):
        user = get_user_model().objects.create_user(
            username="tcg-tester",
            password="pass12345",
        )
        game = Game.objects.create(created_by=user, active_tcg_type="water")
        engine = GameEngine(game)
        player = engine.add_player(user)
        expected_by_instance = {}

        for order_index, pokemon_card in enumerate(self.cards, start=1):
            game_card = GameCard.objects.create(
                game=game,
                pokemon_card=pokemon_card,
                location=GameCard.Location.MAIN,
                owner=player,
                order_index=order_index,
            )
            expected_by_instance[game_card.pk] = (
                pokemon_card.tcg_type,
                pokemon_card.get_tcg_type_display(),
                engine.requires_tcg_type_choice(pokemon_card),
            )

        top_discard = GameCard.objects.create(
            game=game,
            pokemon_card=self.cards[0],
            location=GameCard.Location.DEFAUSSE,
            order_index=len(self.cards) + 1,
        )

        state = engine.get_game_state(for_player=player)
        serialized_player = next(entry for entry in state["players"] if entry["id"] == player.pk)
        serialized_cards = serialized_player["hand"]

        self.assertEqual(len(serialized_cards), 22)
        self.assertEqual(state["active_tcg_type"]["slug"], "water")
        self.assertEqual(len(state["available_tcg_types"]), 4)
        self.assertEqual(
            {entry["slug"] for entry in state["available_tcg_types"]},
            EXPECTED_TCG_TYPE_SLUGS,
        )
        self.assertEqual(state["top_discard"]["id"], top_discard.pk)

        for serialized_card in [*serialized_cards, state["top_discard"]]:
            with self.subTest(game_card=serialized_card["id"]):
                self.assertIn(serialized_card["tcg_type"], EXPECTED_TCG_TYPE_SLUGS)
                self.assertIn("tcg_type_label", serialized_card)
                self.assertIn("requires_tcg_type_choice", serialized_card)
                for legacy_key in (
                    "families",
                    "requires_family_choice",
                    "requires_declared_type",
                    "primary_type",
                    "secondary_type",
                ):
                    self.assertNotIn(legacy_key, serialized_card)

        for serialized_card in serialized_cards:
            self.assertEqual(
                (
                    serialized_card["tcg_type"],
                    serialized_card["tcg_type_label"],
                    serialized_card["requires_tcg_type_choice"],
                ),
                expected_by_instance[serialized_card["id"]],
            )

        for legacy_key in ("active_family", "available_families", "active_type"):
            self.assertNotIn(legacy_key, state)
