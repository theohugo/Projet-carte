"""Comparaison des noms de Pokémon saisis par les joueurs.

Deux jeux demandent d'écrire un nom au clavier : la saisie doit tolérer les
accents, la casse, les espaces et la ponctuation décorative (« M. Mime »,
« Nidoran♀ »), sans pour autant accepter n'importe quoi. Le nom anglais est
accepté au même titre que le français : le catalogue porte les deux.
"""

import unicodedata

# Les deux jeux de devinette se limitent à la première génération : au-delà,
# reconnaître une silhouette ou dessiner l'espèce devient un jeu de spécialiste.
GEN_ONE_MAX_POKEDEX_ID = 151


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
