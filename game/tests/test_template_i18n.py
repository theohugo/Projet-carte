from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from django.utils.translation import override

from game.models import PokemonCard


@override_settings(LANGUAGES=(("fr", "Français"), ("en", "English")))
class BilingualTemplateTagTests(SimpleTestCase):
    def render(self, language):
        template = Template('{% load poketable_i18n %}{% bilingual "Créer une table" "Create a table" %}')
        with override(language):
            return template.render(Context())

    def test_french_is_the_default_copy(self):
        self.assertEqual(self.render("fr"), "Créer une table")

    def test_english_copy_follows_active_language(self):
        self.assertEqual(self.render("en"), "Create a table")

    def test_localized_name_filter_uses_the_active_language(self):
        card = PokemonCard(name_fr="Bulbizarre", name_en="Bulbasaur")
        template = Template("{% load poketable_i18n %}{{ card|localized_name }}")

        with override("en"):
            self.assertEqual(template.render(Context({"card": card})), "Bulbasaur")
