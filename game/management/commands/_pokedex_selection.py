"""Sélection de 54 Pokémon équilibrée sur les 18 types.

Chaque type apparaît 4 ou 5 fois dans le catalogue. Un double-type compte dans
ses deux catégories. Avec deux exemplaires par espèce, une partie contient donc
8 à 10 cartes de chaque type tout en conservant une pioche de 108 cartes.
"""

STARTER_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

LEGENDARY_IDS = [144, 145, 146, 150, 151]

# Sélection optimisée sous contraintes : 54 espèces, 4 à 5 occurrences par type,
# les trois lignées de starters et les cinq légendaires/mythiques de la Gen 1.
EXTRA_IDS = [
    10,  # Caterpie — Bug
    11,  # Metapod — Bug
    19,  # Rattata — Normal
    25,  # Pikachu — Electric
    27,  # Sandshrew — Ground
    35,  # Clefairy — Fairy
    36,  # Clefable — Fairy
    46,  # Paras — Bug/Grass
    54,  # Psyduck — Water
    56,  # Mankey — Fighting
    57,  # Primeape — Fighting
    63,  # Abra — Psychic
    65,  # Alakazam — Psychic
    66,  # Machop — Fighting
    74,  # Geodude — Rock/Ground
    75,  # Graveler — Rock/Ground
    81,  # Magnemite — Electric/Steel
    92,  # Gastly — Ghost/Poison
    94,  # Gengar — Ghost/Poison
    95,  # Onix — Rock/Ground
    106,  # Hitmonlee — Fighting
    122,  # Mr. Mime — Psychic/Fairy
    131,  # Lapras — Water/Ice
    132,  # Ditto — Normal
    133,  # Eevee — Normal
    135,  # Jolteon — Electric
    137,  # Porygon — Normal
    143,  # Snorlax — Normal
    147,  # Dratini — Dragon
    148,  # Dragonair — Dragon
    149,  # Dragonite — Dragon/Flying
    197,  # Umbreon — Dark
    205,  # Forretress — Bug/Steel
    208,  # Steelix — Steel/Ground
    215,  # Sneasel — Dark/Ice
    228,  # Houndour — Dark/Fire
    248,  # Tyranitar — Rock/Dark
    303,  # Mawile — Steel/Fairy
    478,  # Froslass — Ice/Ghost
    887,  # Dragapult — Dragon/Ghost
]

CURATED_POKEDEX_IDS = sorted(set(STARTER_IDS + LEGENDARY_IDS + EXTRA_IDS))

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
