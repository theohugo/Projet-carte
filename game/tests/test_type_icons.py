from django.conf import settings
from django.template import Context, Template
from django.test import TestCase

from game.pokemon_types import POKEMON_TYPES
from game.type_icons import ICONS_DIR, type_icon_url


class TypeIconTests(TestCase):
    def test_every_type_of_the_game_has_its_official_png(self):
        for pokemon_type in POKEMON_TYPES:
            with self.subTest(type=pokemon_type.slug):
                self.assertTrue((ICONS_DIR / f"{pokemon_type.slug}.png").is_file())

    def test_no_icon_is_left_over(self):
        known = {f"{pokemon_type.slug}.png" for pokemon_type in POKEMON_TYPES}

        self.assertEqual({path.name for path in ICONS_DIR.glob("*.png")}, known)

    def test_an_unknown_type_has_no_url(self):
        self.assertEqual(type_icon_url("chocolat"), "")
        self.assertEqual(type_icon_url(None), "")

    def test_the_tag_renders_the_png_of_the_type(self):
        markup = Template('{% load icons %}{% type_icon "water" %}').render(Context())

        self.assertIn("game/img/types/water.png", markup)
        self.assertIn('class="type-icon"', markup)

    def test_the_tag_stays_silent_on_an_unknown_type(self):
        markup = Template('{% load icons %}{% type_icon "chocolat" %}').render(Context())

        self.assertEqual(markup, "")

    def test_card_art_rules_do_not_resize_nested_type_icons(self):
        stylesheets = [
            settings.BASE_DIR / "static" / "atoms.css",
            settings.BASE_DIR / "static" / "molecules.css",
            settings.BASE_DIR / "static" / "organisms.css",
        ]

        combined_css = "\n".join(path.read_text() for path in stylesheets)

        self.assertIn(".card-unit > img", combined_css)
        self.assertNotIn(".card-unit img", combined_css)
        self.assertNotIn(".card-unit.has-action img", combined_css)
