from django import template
from django.utils.translation import get_language

from game.pokemon_names import localized_value

register = template.Library()


@register.simple_tag
def bilingual(french, english):
    """Return the copy matching Django's active French or English language."""

    language = (get_language() or "fr").lower()
    return english if language.startswith("en") else french


@register.filter
def localized_name(value):
    """Render a Pokémon or type model using its localized name fields."""

    return localized_value(value)
