import json
import tempfile
from pathlib import Path

from django.core.management import call_command
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

    def test_running_twice_is_idempotent(self):
        call_command("seed_pokemon_cards", fixture=self.fixture_path)
        call_command("seed_pokemon_cards", fixture=self.fixture_path)
        self.assertEqual(PokemonCard.objects.count(), 2)
        self.assertEqual(PokemonType.objects.count(), 2)
