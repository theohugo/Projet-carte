"""Saisons de cartes : un même Pokémon, plusieurs éditions à collectionner.

Une saison ne change rien au catalogue de jeu (``PokemonCard``) : elle décrit
une édition de cartes — ses visuels, ses raretés et ses boosters. La collection
est donc doublée, pas remplacée : posséder Dracaufeu en saison 1 ne le donne
pas en saison 2.

Saison 1, le Set de Base : les impressions historiques, trois raretés.
Saison 2, la série 151 : la réédition moderne, qui ajoute les cartes *ex* —
douze Pokémon dont on affiche l'illustration pleine page.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Season:
    number: int
    key: str
    label: str
    kicker: str
    tagline: str
    # Fichier de visuels dans ``game/fixtures``.
    fixture: str
    # Les cartes ex n'existent qu'à partir de la série 151.
    has_ex: bool


SEASON_BASE = 1
SEASON_151 = 2
DEFAULT_SEASON = SEASON_BASE

SEASONS = (
    Season(
        number=SEASON_BASE,
        key="base",
        label="Set de Base",
        kicker="Saison 1",
        tagline="Les 151 cartes de la première édition.",
        fixture="tcg_card_images.json",
        has_ex=False,
    ),
    Season(
        number=SEASON_151,
        key="s151",
        label="Série 151",
        kicker="Saison 2",
        tagline="La réédition moderne, et ses douze cartes ex pleine illustration.",
        fixture="tcg_card_images_151.json",
        has_ex=True,
    ),
)

SEASONS_BY_NUMBER = {season.number: season for season in SEASONS}

# Les douze Pokémon qui ont une carte ex dans la série 151. Leur visuel est
# l'illustration spéciale du set, pas l'impression ordinaire.
EX_POKEDEX_IDS = frozenset((3, 6, 9, 24, 38, 40, 65, 76, 115, 124, 145, 151))


def get_season(number) -> Season:
    """La saison demandée, ou la saison 1 si le numéro ne veut rien dire.

    Tolère ``None`` et les chaînes : le numéro vient souvent d'une URL.
    """

    try:
        return SEASONS_BY_NUMBER[int(number)]
    except (TypeError, ValueError, KeyError):
        return SEASONS_BY_NUMBER[DEFAULT_SEASON]


def is_ex(pokedex_id: int, season: int = DEFAULT_SEASON) -> bool:
    """Ce Pokémon a-t-il une carte ex dans cette saison ?"""

    return get_season(season).has_ex and pokedex_id in EX_POKEDEX_IDS
