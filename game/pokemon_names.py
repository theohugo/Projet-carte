"""Comparaison des noms de Pokémon saisis par les joueurs.

Deux jeux demandent d'écrire un nom au clavier : la saisie doit tolérer les
accents, la casse, les espaces et la ponctuation décorative (« M. Mime »,
« Nidoran♀ »), sans pour autant accepter n'importe quoi. Le nom anglais est
accepté au même titre que le français : le catalogue porte les deux.
"""

import unicodedata

from django.conf import settings
from django.utils.translation import get_language

# Les deux jeux de devinette se limitent à la première génération : au-delà,
# reconnaître une silhouette ou dessiner l'espèce devient un jeu de spécialiste.
GEN_ONE_MAX_POKEDEX_ID = 151

BOT_NAME_EN = {
    "Aquali": "Vaporeon",
    "Carapuce": "Squirtle",
    "Lokhlass": "Lapras",
    "Métalosse": "Metagross",
    "Métamorph": "Ditto",
    "Mimiqui": "Mimikyu",
    "Motisma": "Rotom",
    "Ondine": "Misty",
    "Pepper": "Arven",
    "Pierre": "Brock",
}


def active_language(language_code: str | None = None) -> str:
    """Return the supported base language used by the current request.

    Django can expose variants such as ``en-us`` or ``fr-fr``.  The product
    only has French and English copy, so variants deliberately collapse to
    their base language and every unsupported value falls back to French.
    """

    value = language_code or get_language() or settings.LANGUAGE_CODE or "fr"
    return "en" if str(value).lower().replace("_", "-").split("-", 1)[0] == "en" else "fr"


def localized_value(
    value,
    *,
    language_code: str | None = None,
    french_field: str = "name_fr",
    english_field: str = "name_en",
) -> str:
    """Pick a translated model value with a French/available-name fallback."""

    french = getattr(value, french_field, "") or ""
    english = getattr(value, english_field, "") or ""
    preferred = english if active_language(language_code) == "en" else french
    fallback = french or english or getattr(value, "slug", "") or ""
    return preferred or fallback


def localized_pokemon_name(pokemon_card, language_code: str | None = None) -> str:
    """Name of a Pokémon in the active request language."""

    return localized_value(pokemon_card, language_code=language_code)


def localized_type_name(pokemon_type, language_code: str | None = None) -> str:
    """Name of a Pokémon type in the active request language."""

    return localized_value(pokemon_type, language_code=language_code)


def bilingual_text(french: str, english: str, language_code: str | None = None) -> str:
    """Pick product copy using the same browser-language rules as Pokémon names."""

    return english if active_language(language_code) == "en" else french


def localized_bot_name(bot_name: str, language_code: str | None = None) -> str:
    """Translate the presentation of stored French ``IA Name`` bot labels."""

    if active_language(language_code) != "en" or not bot_name.startswith("IA "):
        return bot_name
    name = bot_name.removeprefix("IA ")
    return f"{BOT_NAME_EN.get(name, name)} AI"


def normalize_name(value) -> str:
    """Réduit un nom à ses lettres et chiffres, sans accent ni casse."""

    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return "".join(char for char in without_accents.lower() if char.isalnum())


def name_matches(guess, pokemon_card) -> bool:
    """Vrai si la saisie correspond au nom français ou anglais de l'espèce."""

    normalized_guess = normalize_name(guess)
    if not normalized_guess:
        return False
    return normalized_guess in {
        normalize_name(pokemon_card.name_fr),
        normalize_name(pokemon_card.name_en),
    }


def letter_hint(name: str) -> str:
    """Indice « première et dernière lettre » : ``P • • • • • U``.

    Les caractères non alphabétiques (tiret, point, symbole de genre) restent
    visibles : ils font partie de la forme du nom sans le donner.
    """

    letters = [index for index, char in enumerate(name) if char.isalpha()]
    if len(letters) <= 2:
        return name

    revealed = {letters[0], letters[-1]}
    return " ".join(
        char if index in revealed or not char.isalpha() else "•" for index, char in enumerate(name)
    )


def letter_count(name: str) -> int:
    """Nombre de lettres du nom, ponctuation exclue."""

    return sum(1 for char in name if char.isalpha())
