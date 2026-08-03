"""Sélection de 22 Pokémon équilibrée sur les quatre types du JCC moderne.

Chaque Pokémon reçoit un unique type JCC explicite. Les catégories contiennent
5 ou 6 espèces, soit 10 à 12 cartes de chaque type avec deux exemplaires, tout
en conservant les trois lignées de starters et les légendaires de la Gen 1
qui appartiennent à l'un des quatre types retenus.
"""

from game.tcg_types import POKEMON_TYPE_TO_TCG_TYPE, TCG_TYPES

STARTER_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

LEGENDARY_IDS = [144, 145, 146]

# Sélection optimisée sous contraintes : 22 espèces et 5 à 6 cartes par type
# JCC, avant duplication dans une partie.
EXTRA_IDS = [
    10,  # Caterpie — Bug
    25,  # Pikachu — Electric
    46,  # Paras — Bug/Grass
    54,  # Psyduck — Water
    58,  # Growlithe — Fire
    81,  # Magnemite — Electric/Steel
    123,  # Scyther — Bug/Flying
    131,  # Lapras — Water/Ice
    135,  # Jolteon — Electric
    181,  # Ampharos — Electric
]

CURATED_POKEDEX_IDS = sorted(set(STARTER_IDS + LEGENDARY_IDS + EXTRA_IDS))

# Affectation volontaire et non dérivée du seul type primaire. Cette table est
# l'autorité du catalogue et garantit une répartition stable même si PokeAPI
# fait évoluer ses données de présentation.
TCG_TYPE_BY_POKEDEX_ID = {
    # Plante — 6
    1: "grass",
    2: "grass",
    3: "grass",
    10: "grass",
    46: "grass",
    123: "grass",
    # Feu — 5
    4: "fire",
    5: "fire",
    6: "fire",
    58: "fire",
    146: "fire",
    # Eau — 6
    7: "water",
    8: "water",
    9: "water",
    54: "water",
    131: "water",
    144: "water",
    # Électrique — 5
    25: "lightning",
    81: "lightning",
    135: "lightning",
    145: "lightning",
    181: "lightning",
}

TCG_TYPE_TARGETS = {
    "grass": 6,
    "fire": 5,
    "water": 6,
    "lightning": 5,
}

ALL_TYPE_SLUGS = [
    "normal",
    "fire",
    "water",
    "electric",
    "grass",
    "ice",
    "fighting",
    "poison",
    "ground",
    "flying",
    "psychic",
    "bug",
    "rock",
    "ghost",
    "dragon",
    "dark",
    "steel",
    "fairy",
]

ALL_TCG_TYPE_SLUGS = [tcg_type.slug for tcg_type in TCG_TYPES]

# Garde-fous exécutés à l'import : une modification accidentelle de la sélection
# doit échouer immédiatement plutôt que de créer silencieusement une pioche
# déséquilibrée.
if len(CURATED_POKEDEX_IDS) != 22:
    raise RuntimeError("La sélection JCC doit contenir exactement 22 Pokémon.")
if set(TCG_TYPE_BY_POKEDEX_ID) != set(CURATED_POKEDEX_IDS):
    raise RuntimeError("Chaque Pokémon sélectionné doit avoir exactement un type JCC explicite.")
if set(POKEMON_TYPE_TO_TCG_TYPE) != set(ALL_TYPE_SLUGS):
    raise RuntimeError("Les 18 types source doivent tous être associés à un type JCC.")
