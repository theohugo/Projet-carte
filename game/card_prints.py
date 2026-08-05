"""Les impressions d'une saison : une carte du set, pas une espèce.

Le Set de Base tient dans une carte par espèce, donc la saison 1 se décrit
entièrement par son numéro de Pokédex. La série 151 non : Dracaufeu y existe
en Double rare, en Ultra Rare pleine page et en Illustration spéciale, et ce
sont trois cartes différentes à collectionner. Une saison à impressions se lit
donc ici plutôt que dans ``tcg_card_images``.

Le fixture est committé (aucun accès réseau au démarrage) ; voir
``manage.py fetch_card_prints`` pour le régénérer.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from game.seasons import get_season

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@dataclass(frozen=True, slots=True)
class CardPrint:
    # Numéro de la carte dans le set : c'est lui qui identifie l'impression.
    local_id: int
    dex_id: int
    name_fr: str
    rarity: str
    image: str

    @property
    def variant(self) -> str:
        """Clé stockée en collection pour distinguer deux tirages d'une espèce."""

        return str(self.local_id)


@cache
def prints_of(season: int) -> tuple[CardPrint, ...]:
    """Toutes les impressions de la saison, dans l'ordre du set."""

    fixture = get_season(season).prints_fixture
    if not fixture:
        return ()

    path = FIXTURES_DIR / fixture
    if not path.exists():
        return ()

    rows = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        CardPrint(
            local_id=row["local_id"],
            dex_id=row["dex_id"],
            name_fr=row["name_fr"],
            rarity=row["rarity"],
            image=row["image"],
        )
        for row in sorted(rows, key=lambda row: row["local_id"])
    )


@cache
def prints_by_variant(season: int) -> dict[str, CardPrint]:
    return {card.variant: card for card in prints_of(season)}


def get_print(season: int, variant: str) -> CardPrint | None:
    return prints_by_variant(season).get(str(variant))
