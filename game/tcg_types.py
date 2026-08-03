"""Référentiel des types du Jeu de Cartes à Collectionner Pokémon.

Les jeux vidéo distinguent 18 types ; le JCC moderne en utilise dix, dont cette
plateforme n'en retient que quatre pour simplifier le jeu (Plante, Feu, Eau et
Électrique — Psy, Combat, Incolore, Obscurité, Métal et Dragon ne sont pas
repris). Une carte du catalogue possède donc un unique type JCC explicite,
même lorsque le Pokémon a deux types dans les jeux vidéo. Les types source
restent conservés sur :class:`PokemonCard` afin de pouvoir afficher les
informations authentiques du Pokémon dans l'interface.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TcgType:
    """Métadonnées stables d'un type de carte du JCC Pokémon."""

    slug: str
    name_fr: str
    name_en: str
    is_basic_energy: bool

    def as_dict(self) -> dict[str, str | bool]:
        """Retourne une représentation JSON-compatible pour l'API de jeu."""

        return {
            "slug": self.slug,
            "name_fr": self.name_fr,
            "name_en": self.name_en,
            "is_basic_energy": self.is_basic_energy,
        }


TCG_TYPES = (
    TcgType("grass", "Plante", "Grass", True),
    TcgType("fire", "Feu", "Fire", True),
    TcgType("water", "Eau", "Water", True),
    TcgType("lightning", "Électrique", "Lightning", True),
)

TCG_TYPE_BY_SLUG = {tcg_type.slug: tcg_type for tcg_type in TCG_TYPES}
TCG_TYPE_CHOICES = tuple((tcg_type.slug, tcg_type.name_fr) for tcg_type in TCG_TYPES)

# Correspondance avec les 18 types des jeux vidéo/PokeAPI, ramenée aux quatre
# types JCC retenus par cette plateforme : Poison, Insecte et Normal/Vol
# rejoignent Plante, Combat/Sol/Roche/Acier rejoignent Feu, Psy/Spectre/
# Ténèbres/Fée/Dragon rejoignent Eau, Glace rejoint Eau également.
POKEMON_TYPE_TO_TCG_TYPE = {
    "normal": "grass",
    "fire": "fire",
    "water": "water",
    "electric": "lightning",
    "grass": "grass",
    "ice": "water",
    "fighting": "fire",
    "poison": "grass",
    "ground": "fire",
    "flying": "grass",
    "psychic": "water",
    "bug": "grass",
    "rock": "fire",
    "ghost": "water",
    "dragon": "water",
    "dark": "water",
    "steel": "fire",
    "fairy": "water",
}

# Couleurs de présentation centralisées pour les consommateurs Python (export,
# génération de previews, etc.). Le CSS peut reprendre les mêmes valeurs.
TCG_TYPE_COLORS = {
    "grass": "#4DAD5B",
    "fire": "#EA5B45",
    "water": "#4C91D8",
    "lightning": "#F2C84B",
}


def get_tcg_type(slug: object) -> TcgType | None:
    """Retourne un type JCC par slug, sans lever d'erreur pour une entrée invalide."""

    if not isinstance(slug, str):
        return None
    return TCG_TYPE_BY_SLUG.get(slug.strip().lower())


def tcg_type_slug_for_source_type(slug: object) -> str | None:
    """Convertit un slug PokeAPI en slug JCC moderne."""

    if not isinstance(slug, str):
        return None
    return POKEMON_TYPE_TO_TCG_TYPE.get(slug.strip().lower())
