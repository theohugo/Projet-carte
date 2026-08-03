"""Sélection curatée de pokedex_id utilisés par `seed_pokemon_cards --from-api`.

Critère de sélection : les 3 lignées de starters Gen 1, les 5 légendaires/mythiques
Gen 1, et au moins 2 Pokémon par type parmi les 18 types. Le Gen 1 ne contient
nativement aucun Pokémon Ténèbres/Acier (types introduits en Gen 2) : quelques
ID Gen 2 sont donc ajoutés spécifiquement pour ces deux types (déviation
assumée, documentée dans le README).
"""

STARTER_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

LEGENDARY_IDS = [144, 145, 146, 150, 151]

# Couverture des 18 types + variété (Gen 1, sauf mention contraire).
EXTRA_IDS = [
    10,  # Caterpie — Bug
    16,  # Pidgey — Normal/Flying
    19,  # Rattata — Normal
    23,  # Ekans — Poison
    25,  # Pikachu — Electric
    27,  # Sandshrew — Ground
    35,  # Clefairy — Fairy
    41,  # Zubat — Poison/Flying
    43,  # Oddish — Grass/Poison
    54,  # Psyduck — Water
    58,  # Growlithe — Fire
    63,  # Abra — Psychic
    65,  # Alakazam — Psychic
    66,  # Machop — Fighting
    74,  # Geodude — Rock/Ground
    79,  # Slowpoke — Water/Psychic
    81,  # Magnemite — Electric/Steel
    83,  # Farfetch'd — Normal/Flying
    88,  # Grimer — Poison
    92,  # Gastly — Ghost/Poison
    94,  # Gengar — Ghost/Poison
    95,  # Onix — Rock/Ground
    106,  # Hitmonlee — Fighting
    109,  # Koffing — Poison
    116,  # Horsea — Water
    122,  # Mr. Mime — Psychic/Fairy
    123,  # Scyther — Bug/Flying
    131,  # Lapras — Water/Ice
    132,  # Ditto — Normal
    133,  # Eevee — Normal
    134,  # Vaporeon — Water
    135,  # Jolteon — Electric
    137,  # Porygon — Normal
    143,  # Snorlax — Normal
    147,  # Dratini — Dragon
    149,  # Dragonite — Dragon/Flying
    # Gen 2 : seule génération disponible pour Ténèbres/Acier natifs.
    197,  # Umbreon — Dark
    228,  # Houndour — Dark/Fire
    208,  # Steelix — Steel/Ground
    227,  # Skarmory — Steel/Flying
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
