from django.template import Context, Template
from django.test import TestCase

from game.templatetags.icons import ICONS


def render(source, **context):
    return Template("{% load icons %}" + source).render(Context(context))


class IconTagTests(TestCase):
    def test_a_known_icon_renders_an_inline_svg(self):
        markup = render('{% icon "coin" %}')

        self.assertIn("<svg", markup)
        self.assertIn('class="icon icon-coin"', markup)
        self.assertIn('stroke="currentColor"', markup)

    def test_an_icon_is_decorative_by_default(self):
        markup = render('{% icon "back" %}')

        self.assertIn('aria-hidden="true"', markup)
        self.assertIn('focusable="false"', markup)

    def test_an_extra_class_is_appended(self):
        markup = render('{% icon "back" "icon-sm" %}')

        self.assertIn('class="icon icon-back icon-sm"', markup)

    def test_an_unknown_icon_renders_nothing(self):
        self.assertEqual(render('{% icon "licorne" %}'), "")

    def test_every_icon_is_drawable(self):
        # Un chemin vide passerait inaperçu jusqu'à l'affichage : on le voit ici.
        for name, body in ICONS.items():
            with self.subTest(icon=name):
                self.assertTrue(body.startswith("<"), name)
                markup = render(f'{{% icon "{name}" %}}')
                self.assertIn("viewBox", markup)
