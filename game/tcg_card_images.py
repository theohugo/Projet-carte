"""Visuels de vraies cartes TCG pour la page Collection.

Ce module ne concerne que l'illustration affichée en Collection : le
catalogue de jeu (``PokemonCard``) reste alimenté par PokeAPI et n'est pas
modifié. Un fixture par saison, tous committés, donc aucun accès réseau n'est
requis au démarrage ; voir ``manage.py fetch_tcg_card_images`` pour les
régénérer.
"""

import json
from functools import cache
from pathlib import Path

from game.seasons import DEFAULT_SEASON, get_season

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@cache
def _load_images(fixture: str) -> dict[str, str]:
    path = FIXTURES_DIR / fixture
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_tcg_image_url(pokedex_id: int, season: int = DEFAULT_SEASON) -> str | None:
    """URL de la carte TCG de cette saison pour ce numéro de Pokédex, si connue."""

    return _load_images(get_season(season).fixture).get(str(pokedex_id))
