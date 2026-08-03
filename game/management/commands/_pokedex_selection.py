"""Sélection de 54 Pokémon équilibrée sur les dix types du JCC moderne.

Chaque Pokémon reçoit un unique type JCC explicite. Les catégories contiennent
5 ou 6 espèces, soit 10 à 12 cartes de chaque type avec deux exemplaires, tout
en conservant les trois lignées de starters et les légendaires de la Gen 1.
"""

from game.tcg_types import POKEMON_TYPE_TO_TCG_TYPE, TCG_TYPES

STARTER_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

LEGENDARY_IDS = [144, 145, 146, 150, 151]

# Sélection optimisée sous contraintes : 54 espèces et 5 à 6 cartes par type
# JCC, avant duplication dans une partie.
EXTRA_IDS = [
    10,  # Caterpie — Bug
    16,  # Roucool — Normal/Flying
    19,  # Rattata — Normal
    25,  # Pikachu — Electric
    35,  # Clefairy — Fairy
    46,  # Paras — Bug/Grass
    54,  # Psyduck — Water
    56,  # Mankey — Fighting
    58,  # Growlithe — Fire
    63,  # Abra — Psychic
    66,  # Machop — Fighting
    74,  # Geodude — Rock/Ground
    81,  # Magnemite — Electric/Steel
    89,  # Muk — Poison
    92,  # Gastly — Ghost/Poison
    94,  # Gengar — Ghost/Poison
    95,  # Onix — Rock/Ground
    106,  # Hitmonlee — Fighting
    122,  # Mr. Mime — Psychic/Fairy
    123,  # Scyther — Bug/Flying
    131,  # Lapras — Water/Ice
    132,  # Ditto — Normal
    133,  # Eevee — Normal
    135,  # Jolteon — Electric
    137,  # Porygon — Normal
    143,  # Snorlax — Normal
    147,  # Dratini — Dragon
    148,  # Dragonair — Dragon
    149,  # Dragonite — Dragon/Flying
    181,  # Ampharos — Electric
    197,  # Umbreon — Dark
    205,  # Forretress — Bug/Steel
    208,  # Steelix — Steel/Ground
    212,  # Scizor — Bug/Steel
    215,  # Sneasel — Dark/Ice
    248,  # Tyranitar — Rock/Dark
    303,  # Mawile — Steel/Fairy
    304,  # Aron — Steel/Rock
    445,  # Garchomp — Dragon/Ground
    887,  # Dragapult — Dragon/Ghost
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
    # Psy — 6
    35: "psychic",
    63: "psychic",
    94: "psychic",
    122: "psychic",
    150: "psychic",
    151: "psychic",
    # Combat — 5
    56: "fighting",
    66: "fighting",
    74: "fighting",
    95: "fighting",
    106: "fighting",
    # Obscurité — 5
    89: "darkness",
    92: "darkness",
    197: "darkness",
    215: "darkness",
    248: "darkness",
    # Métal — 5
    205: "metal",
    208: "metal",
    212: "metal",
    303: "metal",
    304: "metal",
    # Dragon — 5
    147: "dragon",
    148: "dragon",
    149: "dragon",
    445: "dragon",
    887: "dragon",
    # Incolore — 6
    16: "colorless",
    19: "colorless",
    132: "colorless",
    133: "colorless",
    137: "colorless",
    143: "colorless",
}

TCG_TYPE_TARGETS = {
    "grass": 6,
    "fire": 5,
    "water": 6,
    "lightning": 5,
    "psychic": 6,
    "fighting": 5,
    "darkness": 5,
    "metal": 5,
    "dragon": 5,
    "colorless": 6,
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
if len(CURATED_POKEDEX_IDS) != 54:
    raise RuntimeError("La sélection JCC doit contenir exactement 54 Pokémon.")
if set(TCG_TYPE_BY_POKEDEX_ID) != set(CURATED_POKEDEX_IDS):
    raise RuntimeError("Chaque Pokémon sélectionné doit avoir exactement un type JCC explicite.")
if set(POKEMON_TYPE_TO_TCG_TYPE) != set(ALL_TYPE_SLUGS):
    raise RuntimeError("Les 18 types source doivent tous être associés à un type JCC.")
