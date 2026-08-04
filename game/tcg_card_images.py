"""Visuels de vraies cartes TCG pour la page Collection.

Ce module ne concerne que l'illustration affichée en Collection : le
catalogue de jeu (``PokemonCard``) reste alimenté par PokeAPI et n'est pas
modifié. Le fixture est committé, donc aucun accès réseau n'est requis au
démarrage ; voir ``manage.py fetch_tcg_card_images`` pour le régénérer.
"""

import json
from functools import lru_cache
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "tcg_card_images.json"


@lru_cache(maxsize=1)
def _load_images() -> dict[str, str]:
    if not FIXTURE_PATH.exists():
        return {}
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def get_tcg_image_url(pokedex_id: int) -> str | None:
    """URL de la carte TCG associée à ce numéro de Pokédex, si connue."""

    return _load_images().get(str(pokedex_id))
