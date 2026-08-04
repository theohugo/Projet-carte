from django.template import Context, Template
from django.test import TestCase

from game.pokemon_types import POKEMON_TYPES
from game.type_glyphs import TYPE_GLYPHS


def render(source):
    return Template("{% load icons %}" + source).render(Context())


class TypeGlyphTests(TestCase):
    def test_every_type_of_the_game_has_a_glyph(self):
        # Un type sans dessin passerait à travers jusqu'à la table de jeu.
        missing = [info.slug for info in POKEMON_TYPES if info.slug not in TYPE_GLYPHS]

        self.assertEqual(missing, [])

    def test_no_glyph_is_left_over(self):
        known = {info.slug for info in POKEMON_TYPES}

        self.assertEqual(set(TYPE_GLYPHS) - known, set())

    def test_the_sprite_holds_one_symbol_per_type(self):
        markup = render("{% type_sprite %}")

        self.assertEqual(markup.count("<symbol"), len(POKEMON_TYPES))
        self.assertIn('id="type-water"', markup)

    def test_an_icon_points_at_the_sprite(self):
        markup = render('{% type_icon "fire" %}')

        self.assertIn('href="#type-fire"', markup)
        self.assertIn('class="type-glyph"', markup)

    def test_an_unknown_type_renders_nothing(self):
        self.assertEqual(render('{% type_icon "chocolat" %}'), "")
