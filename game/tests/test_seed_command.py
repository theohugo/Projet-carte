import json
import tempfile
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from game.models import PokemonCard, PokemonType

SAMPLE_FIXTURE = {
    "types": [
        {"slug": "fire", "name_fr": "Feu", "name_en": "Fire"},
        {"slug": "water", "name_fr": "Eau", "name_en": "Water"},
    ],
    "cards": [
        {
            "pokedex_id": 4,
            "slug": "charmander",
            "name_fr": "Salamèche",
            "name_en": "Charmander",
            "primary_type": "fire",
            "secondary_type": None,
            "sprite_url": "https://example.com/4.png",
            "is_legendary": False,
            "action": "DRAW_TWO",
            "tcg_type": "fire",
        },
        {
            "pokedex_id": 7,
            "slug": "squirtle",
            "name_fr": "Carapuce",
            "name_en": "Squirtle",
            "primary_type": "water",
            "secondary_type": None,
            "sprite_url": "https://example.com/7.png",
            "is_legendary": False,
            "tcg_type": "water",
        },
    ],
}


class SeedPokemonCardsTests(TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.fixture_path = Path(tmp_dir.name) / "sample.json"
        self.fixture_path.write_text(json.dumps(SAMPLE_FIXTURE), encoding="utf-8")

    def test_loads_types_and_cards_from_fixture(self):
        call_command("seed_pokemon_cards", fixture=self.fixture_path)
        self.assertEqual(PokemonType.objects.count(), 2)
        self.assertEqual(PokemonCard.objects.count(), 2)
        self.assertTrue(PokemonCard.objects.filter(pokedex_id=4, name_fr="Salamèche").exists())
        self.assertEqual(PokemonCard.objects.get(pokedex_id=4).action, PokemonCard.Action.DRAW_TWO)
        self.assertEqual(PokemonCard.objects.get(pokedex_id=7).action, PokemonCard.Action.NORMAL)
        self.assertEqual(PokemonCard.objects.get(pokedex_id=4).tcg_type, "fire")
        self.assertEqual(PokemonCard.objects.get(pokedex_id=7).tcg_type, "water")

    def test_catalogue_species_are_loaded_outside_the_current_deck(self):
        fixture = dict(SAMPLE_FIXTURE)
        fixture["catalogue"] = [
            {
                "pokedex_id": 25,
                "slug": "pikachu",
                "name_fr": "Pikachu",
                "name_en": "Pikachu",
                "primary_type": "fire",
                "secondary_type": None,
                "sprite_url": "https://example.com/25.png",
                "is_legendary": False,
            }
        ]
        self.fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

        call_command("seed_pokemon_cards", fixture=self.fixture_path)

        self.assertEqual(PokemonCard.objects.count(), 3)
        self.assertEqual(PokemonCard.objects.filter(in_current_deck=True).count(), 2)
        self.assertFalse(PokemonCard.objects.get(pokedex_id=25).in_current_deck)

    def test_running_twice_is_idempotent(self):
        call_command("seed_pokemon_cards", fixture=self.fixture_path)
        call_command("seed_pokemon_cards", fixture=self.fixture_path)
        self.assertEqual(PokemonCard.objects.count(), 2)
        self.assertEqual(PokemonType.objects.count(), 2)

    def test_cards_removed_from_the_fixture_are_kept_but_deactivated(self):
        stale = PokemonCard.objects.create(
            pokedex_id=999,
            slug="stale",
            name_fr="Ancienne",
            name_en="Stale",
            primary_type=PokemonType.objects.create(slug="old", name_fr="Ancien", name_en="Old"),
            sprite_url="https://example.com/999.png",
        )

        call_command("seed_pokemon_cards", fixture=self.fixture_path)

        stale.refresh_from_db()
        self.assertFalse(stale.in_current_deck)
        self.assertEqual(PokemonCard.objects.filter(in_current_deck=True).count(), 2)

    def test_derives_tcg_type_for_a_custom_fixture_without_explicit_value(self):
        data = json.loads(json.dumps(SAMPLE_FIXTURE))
        data["cards"][0].pop("tcg_type")
        self.fixture_path.write_text(json.dumps(data), encoding="utf-8")

        call_command("seed_pokemon_cards", fixture=self.fixture_path)

        self.assertEqual(PokemonCard.objects.get(pokedex_id=4).tcg_type, "fire")

    def test_rejects_an_unknown_explicit_tcg_type(self):
        data = json.loads(json.dumps(SAMPLE_FIXTURE))
        data["cards"][0]["tcg_type"] = "cosmic"
        self.fixture_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesMessage(CommandError, "Type JCC invalide"):
            call_command("seed_pokemon_cards", fixture=self.fixture_path)
