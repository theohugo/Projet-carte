"""Pictogrammes officiels des 18 types Pokémon, en PNG.

Ce sont les vraies pastilles rondes des jeux : le symbole blanc sur le disque
de couleur du type. Elles remplacent les tracés SVG maison, qui approximaient
les symboles sans jamais être les bons.

Les fichiers sont servis depuis nos statiques (aucune requête vers un domaine
tiers, aucun visuel qui disparaît si la source bouge) ; voir
``manage.py fetch_type_icons`` pour les régénérer.
"""

from pathlib import Path

from django.templatetags.static import static

from game.pokemon_types import POKEMON_TYPE_SLUGS

ICONS_DIR = Path(__file__).resolve().parent / "static" / "game" / "img" / "types"
STATIC_PREFIX = "game/img/types"


def icon_path(slug: str) -> str:
    """Chemin statique du pictogramme, tel qu'on le passe à ``{% static %}``."""

    return f"{STATIC_PREFIX}/{slug}.png"


def type_icon_url(slug) -> str:
    """URL servie du pictogramme d'un type, vide si le type est inconnu.

    L'URL est résolue à l'appel et non à l'import : en production le nom des
    fichiers porte une empreinte, connue seulement après ``collectstatic``.
    """

    if slug not in POKEMON_TYPE_SLUGS:
        return ""
    return static(icon_path(slug))
