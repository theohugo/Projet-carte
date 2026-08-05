from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import translation

from game.pokemon_names import (
    active_language,
    localized_bot_name,
    localized_pokemon_name,
    localized_type_name,
)


class LocalizedPokemonNameTests(SimpleTestCase):
    def setUp(self):
        self.value = SimpleNamespace(
            name_fr="Bulbizarre",
            name_en="Bulbasaur",
            slug="bulbasaur",
        )

    def test_language_variants_use_the_expected_catalogue_field(self):
        self.assertEqual(localized_pokemon_name(self.value, "fr-FR"), "Bulbizarre")
        self.assertEqual(localized_pokemon_name(self.value, "en-US"), "Bulbasaur")
        self.assertEqual(localized_type_name(self.value, "en-GB"), "Bulbasaur")

    def test_the_active_django_language_is_used_by_default(self):
        with translation.override("en"):
            self.assertEqual(active_language(), "en")
            self.assertEqual(localized_pokemon_name(self.value), "Bulbasaur")

    def test_missing_translations_fall_back_to_french_then_available_name(self):
        without_english = SimpleNamespace(name_fr="Électrik", name_en="", slug="electric")
        without_french = SimpleNamespace(name_fr="", name_en="Electric", slug="electric")

        self.assertEqual(localized_type_name(without_english, "en"), "Électrik")
        self.assertEqual(localized_type_name(without_french, "fr"), "Electric")

    def test_bot_labels_are_localized_without_changing_the_stored_value(self):
        self.assertEqual(localized_bot_name("IA Métalosse", "fr"), "IA Métalosse")
        self.assertEqual(localized_bot_name("IA Métalosse", "en"), "Metagross AI")
        self.assertEqual(localized_bot_name("IA Porygon", "en-US"), "Porygon AI")
        self.assertEqual(localized_bot_name("Bot 1", "en"), "Bot 1")
