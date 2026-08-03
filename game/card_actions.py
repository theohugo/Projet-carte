"""Répartition stable des effets spéciaux dans le catalogue Poké-Uno.

Les effets ne dépendent pas d'un tirage aléatoire : une même espèce conserve
toujours son pouvoir, ce qui permet aux joueurs d'apprendre les cartes et au
constructeur de paquet d'en garantir la quantité.
"""

from game.models import PokemonCard

ACTION_BY_POKEDEX_ID = {
    25: PokemonCard.Action.DRAW_TWO,
    66: PokemonCard.Action.DRAW_TWO,
    94: PokemonCard.Action.DRAW_TWO,
    149: PokemonCard.Action.DRAW_TWO,
    150: PokemonCard.Action.DRAW_FOUR,
    151: PokemonCard.Action.DRAW_FOUR,
    36: PokemonCard.Action.REVERSE,
    122: PokemonCard.Action.REVERSE,
    132: PokemonCard.Action.REVERSE,
    137: PokemonCard.Action.REVERSE,
    9: PokemonCard.Action.SHIELD,
    95: PokemonCard.Action.SHIELD,
    143: PokemonCard.Action.SHIELD,
    208: PokemonCard.Action.SHIELD,
}


def action_for_pokedex_id(pokedex_id: int) -> str:
    return ACTION_BY_POKEDEX_ID.get(pokedex_id, PokemonCard.Action.NORMAL)
