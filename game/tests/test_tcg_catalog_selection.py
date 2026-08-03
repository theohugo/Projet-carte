import json
from collections import Counter
from pathlib import Path

from django.test import SimpleTestCase

from game.management.commands._pokedex_selection import (
    ALL_TYPE_SLUGS,
    CURATED_POKEDEX_IDS,
    EXTRA_IDS,
    LEGENDARY_IDS,
    STARTER_IDS,
    TCG_TYPE_BY_POKEDEX_ID,
    TCG_TYPE_TARGETS,
)
from game.tcg_types import (
    POKEMON_TYPE_TO_TCG_TYPE,
    TCG_TYPE_BY_SLUG,
    TCG_TYPE_CHOICES,
    TCG_TYPES,
    get_tcg_type,
    tcg_type_slug_for_source_type,
)


class TcgTypeCatalogTests(SimpleTestCase):
    def test_exposes_the_four_modern_card_types_in_display_order(self):
        expected_slugs = (
            "grass",
            "fire",
            "water",
            "lightning",
        )

        self.assertEqual(tuple(tcg_type.slug for tcg_type in TCG_TYPES), expected_slugs)
        self.assertEqual(tuple(TCG_TYPE_BY_SLUG), expected_slugs)
        self.assertEqual(tuple(slug for slug, _label in TCG_TYPE_CHOICES), expected_slugs)
        self.assertEqual(
            {tcg_type.slug for tcg_type in TCG_TYPES if not tcg_type.is_basic_energy},
            set(),
        )

    def test_maps_every_source_type_to_a_valid_tcg_type(self):
        self.assertEqual(set(POKEMON_TYPE_TO_TCG_TYPE), set(ALL_TYPE_SLUGS))
        self.assertLessEqual(set(POKEMON_TYPE_TO_TCG_TYPE.values()), set(TCG_TYPE_BY_SLUG))
        self.assertEqual(tcg_type_slug_for_source_type("electric"), "lightning")
        self.assertEqual(tcg_type_slug_for_source_type(" fairy "), "water")
        self.assertEqual(tcg_type_slug_for_source_type("poison"), "grass")

    def test_lookup_helpers_are_safe_for_unknown_or_non_string_values(self):
        self.assertEqual(get_tcg_type(" FIRE ").name_fr, "Feu")
        self.assertEqual(
            get_tcg_type("water").as_dict(),
            {
                "slug": "water",
                "name_fr": "Eau",
                "name_en": "Water",
                "is_basic_energy": True,
            },
        )
        self.assertIsNone(get_tcg_type("unknown"))
        self.assertIsNone(get_tcg_type(None))
        self.assertIsNone(tcg_type_slug_for_source_type(25))


class CuratedTcgSelectionTests(SimpleTestCase):
    EXPECTED_EXTRA_IDS = {
        10,
        25,
        46,
        54,
        58,
        81,
        123,
        131,
        135,
        181,
    }

    def test_selection_contains_exactly_the_requested_22_pokemon(self):
        self.assertEqual(len(CURATED_POKEDEX_IDS), 22)
        self.assertEqual(len(set(CURATED_POKEDEX_IDS)), 22)
        self.assertEqual(set(EXTRA_IDS), self.EXPECTED_EXTRA_IDS)
        self.assertLessEqual(set(STARTER_IDS), set(CURATED_POKEDEX_IDS))
        self.assertLessEqual(set(LEGENDARY_IDS), set(CURATED_POKEDEX_IDS))
        self.assertEqual(set(TCG_TYPE_BY_POKEDEX_ID), set(CURATED_POKEDEX_IDS))

    def test_selection_matches_the_exact_balance_targets(self):
        counts = Counter(TCG_TYPE_BY_POKEDEX_ID.values())

        self.assertEqual(dict(counts), TCG_TYPE_TARGETS)
        self.assertEqual(sum(counts.values()), 22)
        self.assertEqual(min(counts.values()), 5)
        self.assertEqual(max(counts.values()), 6)

    def test_committed_fixture_matches_the_curated_selection_and_types(self):
        fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "pokemon_cards.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        cards_by_id = {card["pokedex_id"]: card for card in data["cards"]}

        self.assertEqual(set(cards_by_id), set(CURATED_POKEDEX_IDS))
        self.assertEqual(
            {pokedex_id: card["tcg_type"] for pokedex_id, card in cards_by_id.items()},
            TCG_TYPE_BY_POKEDEX_ID,
        )
        self.assertEqual(Counter(card["tcg_type"] for card in cards_by_id.values()), TCG_TYPE_TARGETS)
