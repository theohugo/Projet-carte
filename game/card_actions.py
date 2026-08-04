"""Répartition des effets spéciaux dans la pioche d'une partie.

La pioche est tirée au sort à chaque partie : les pouvoirs ne peuvent donc plus
être attachés définitivement à une espèce du catalogue, sans quoi la plupart des
parties n'auraient aucune carte à effet. Ils sont distribués par quotas calculés
sur le nombre d'espèces tirées, dans les proportions d'un jeu de Uno (environ un
tiers de cartes à effet).

Une espèce conserve le même pouvoir pendant toute la partie : les deux
exemplaires d'un Pokémon sont identiques, et les joueurs peuvent mémoriser les
cartes déjà vues.
"""

from game.models import GameCard

# Part des espèces tirées recevant chaque effet. Le +4 est deux fois plus rare :
# c'est le joker qui impose un type en plus d'infliger la plus lourde pénalité.
ACTION_SHARES = (
    (GameCard.Action.DRAW_TWO, 0.10),
    (GameCard.Action.REVERSE, 0.10),
    (GameCard.Action.SHIELD, 0.10),
    (GameCard.Action.DRAW_FOUR, 0.05),
)


def assign_actions(species, rng) -> dict[int, str]:
    """Associe un pouvoir à une partie des espèces tirées.

    Les légendaires sont déjà des jokers par leur rareté : ils ne reçoivent pas
    d'effet supplémentaire. Renvoie ``{pk d'espèce: pouvoir}`` ; les espèces
    absentes du dictionnaire sont des cartes normales.
    """

    candidates = sorted(
        (card for card in species if not card.is_legendary),
        key=lambda card: card.pokedex_id,
    )
    rng.shuffle(candidates)

    actions = {}
    cursor = 0
    for action, share in ACTION_SHARES:
        count = max(0, min(round(len(species) * share), len(candidates) - cursor))
        for card in candidates[cursor : cursor + count]:
            actions[card.pk] = action
        cursor += count
    return actions
