"""Saisons de cartes : un même Pokémon, plusieurs éditions à collectionner.

Une saison ne change rien au catalogue de jeu (``PokemonCard``) : elle décrit
une édition de cartes — ses visuels, ses raretés et ses boosters. La collection
est donc doublée, pas remplacée : posséder Dracaufeu en saison 1 ne le donne
pas en saison 2.

Deux façons de décrire une saison, selon le set :

* **une carte par espèce** (``fixture``) — le Set de Base, où le numéro de
  Pokédex suffit à désigner la carte ;
* **une entrée par impression** (``prints_fixture``) — la série 151, où
  Dracaufeu existe en Double rare, en Ultra Rare pleine page et en
  Illustration spéciale, soit trois cartes distinctes à collectionner.
"""

from dataclasses import dataclass

from game.pokemon_names import bilingual_text


@dataclass(frozen=True, slots=True)
class Season:
    number: int
    key: str
    label: str
    label_en: str
    kicker: str
    kicker_en: str
    tagline: str
    tagline_en: str
    # Visuels par numéro de Pokédex, pour une saison à une carte par espèce.
    fixture: str
    # Impressions du set, pour une saison à plusieurs raretés par espèce.
    prints_fixture: str

    @property
    def display_label(self):
        return bilingual_text(self.label, self.label_en)

    @property
    def display_kicker(self):
        return bilingual_text(self.kicker, self.kicker_en)

    @property
    def display_tagline(self):
        return bilingual_text(self.tagline, self.tagline_en)


SEASON_BASE = 1
SEASON_151 = 2
DEFAULT_SEASON = SEASON_BASE

SEASONS = (
    Season(
        number=SEASON_BASE,
        key="base",
        label="Set de Base",
        label_en="Base Set",
        kicker="Saison 1",
        kicker_en="Season 1",
        tagline="Les 151 cartes de la première édition.",
        tagline_en="The 151 cards from the first edition.",
        fixture="tcg_card_images.json",
        prints_fixture="",
    ),
    Season(
        number=SEASON_151,
        key="s151",
        label="Série 151",
        label_en="151 Series",
        kicker="Saison 2",
        kicker_en="Season 2",
        tagline="Les 185 cartes du set, de la commune à la Rare Or.",
        tagline_en="All 185 cards, from Common to Hyper Rare.",
        fixture="",
        prints_fixture="set_151_prints.json",
    ),
)

SEASONS_BY_NUMBER = {season.number: season for season in SEASONS}


def get_season(number) -> Season:
    """La saison demandée, ou la saison 1 si le numéro ne veut rien dire.

    Tolère ``None`` et les chaînes : le numéro vient souvent d'une URL.
    """

    try:
        return SEASONS_BY_NUMBER[int(number)]
    except (TypeError, ValueError, KeyError):
        return SEASONS_BY_NUMBER[DEFAULT_SEASON]


def has_prints(number) -> bool:
    """La saison se collectionne-t-elle par impression plutôt que par espèce ?"""

    return bool(get_season(number).prints_fixture)
