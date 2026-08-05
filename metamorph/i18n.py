from django.utils.translation import get_language, gettext


def is_english() -> bool:
    return (get_language() or "fr").lower().startswith("en")


def text(french: str, english: str) -> str:
    translated = gettext(french)
    return english if is_english() and translated == french else translated


def pokemon_name(card) -> str:
    return card.name_en if is_english() else card.name_fr
