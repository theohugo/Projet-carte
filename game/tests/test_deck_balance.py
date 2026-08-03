from collections import Counter
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from game.deck_builder import (
    MAX_NORMAL_CARD_COPIES,
    allocate_balanced_copies,
    build_balanced_card_pool,
    count_cards_per_tcg_type,
)
from game.models import PokemonCard
from game.tests.factories import make_cards, make_types


class BalancedDeckTests(TestCase):
    def setUp(self):
        self.cards = make_cards(make_types())

    def _catalogue(self):
        return list(PokemonCard.objects.select_related("primary_type", "secondary_type").all())

    def test_allocation_is_deterministic_and_preserves_every_pokemon(self):
        cards = self._catalogue()
        target_size = len(cards) * 2

        first = allocate_balanced_copies(cards, target_size=target_size)
        second = allocate_balanced_copies(list(reversed(cards)), target_size=target_size)

        self.assertEqual(first, second)
        self.assertEqual(sum(first.values()), target_size)
        self.assertTrue(all(copy_count >= 1 for copy_count in first.values()))

    def test_action_cards_stay_at_two_copies(self):
        action_card = self.cards["zapdos"]
        action_card.action = PokemonCard.Action.DRAW_FOUR
        action_card.save(update_fields=["action"])
        cards = self._catalogue()

        pool = build_balanced_card_pool(cards, target_size=len(cards) * 2)
        copies_by_card = Counter(card.pk for card in pool)

        self.assertEqual(copies_by_card[action_card.pk], 2)
        for card in cards:
            if card.action == PokemonCard.Action.NORMAL:
                self.assertLessEqual(copies_by_card[card.pk], MAX_NORMAL_CARD_COPIES)

    def test_real_catalogue_and_two_copy_deck_are_balanced_by_tcg_type(self):
        PokemonCard.objects.all().delete()
        call_command("seed_pokemon_cards", stdout=StringIO())
        cards = self._catalogue()
        balanced_pool = build_balanced_card_pool(cards, target_size=len(cards) * 2)

        catalogue_counts = count_cards_per_tcg_type(cards)
        balanced_counts = count_cards_per_tcg_type(balanced_pool)
        copies_by_card = Counter(card.pk for card in balanced_pool)

        self.assertEqual(len(cards), 22)
        self.assertEqual(len(catalogue_counts), 4)
        self.assertEqual(
            (min(catalogue_counts.values()), max(catalogue_counts.values())),
            (5, 6),
        )
        self.assertEqual(len(balanced_counts), 4)
        self.assertEqual(
            (min(balanced_counts.values()), max(balanced_counts.values())),
            (10, 12),
        )
        self.assertEqual(len(balanced_pool), 44)
        for card in cards:
            self.assertEqual(copies_by_card[card.pk], 2)

    def test_dual_source_types_do_not_duplicate_the_unique_tcg_type(self):
        dual_type = self.cards["zapdos"]
        dual_type.secondary_type = self.cards["bulbasaur"].primary_type
        dual_type.tcg_type = "lightning"
        dual_type.save(update_fields=["secondary_type", "tcg_type"])

        counts = count_cards_per_tcg_type([dual_type])

        self.assertEqual(counts, Counter({"lightning": 1}))
