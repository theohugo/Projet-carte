"""Référentiel des types du Jeu de Cartes à Collectionner Pokémon.

Les jeux vidéo distinguent 18 types, tandis que le JCC moderne en utilise dix.
Une carte du catalogue possède donc un unique type JCC explicite, même lorsque
le Pokémon a deux types dans les jeux vidéo. Les types source restent conservés
sur :class:`PokemonCard` afin de pouvoir afficher les informations authentiques
du Pokémon dans l'interface.
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
    TcgType("psychic", "Psy", "Psychic", True),
    TcgType("fighting", "Combat", "Fighting", True),
    TcgType("darkness", "Obscurité", "Darkness", True),
    TcgType("metal", "Métal", "Metal", True),
    TcgType("dragon", "Dragon", "Dragon", False),
    TcgType("colorless", "Incolore", "Colorless", False),
)

TCG_TYPE_BY_SLUG = {tcg_type.slug: tcg_type for tcg_type in TCG_TYPES}
TCG_TYPE_CHOICES = tuple((tcg_type.slug, tcg_type.name_fr) for tcg_type in TCG_TYPES)

# Correspondance avec les 18 types des jeux vidéo/PokeAPI. Le type Fée n'est
# plus imprimé dans le JCC moderne et rejoint Psy ; Poison rejoint Obscurité.
POKEMON_TYPE_TO_TCG_TYPE = {
    "normal": "colorless",
    "fire": "fire",
    "water": "water",
    "electric": "lightning",
    "grass": "grass",
    "ice": "water",
    "fighting": "fighting",
    "poison": "darkness",
    "ground": "fighting",
    "flying": "colorless",
    "psychic": "psychic",
    "bug": "grass",
    "rock": "fighting",
    "ghost": "psychic",
    "dragon": "dragon",
    "dark": "darkness",
    "steel": "metal",
    "fairy": "psychic",
}

# Couleurs de présentation centralisées pour les consommateurs Python (export,
# génération de previews, etc.). Le CSS peut reprendre les mêmes valeurs.
TCG_TYPE_COLORS = {
    "grass": "#4DAD5B",
    "fire": "#EA5B45",
    "water": "#4C91D8",
    "lightning": "#F2C84B",
    "psychic": "#A966B7",
    "fighting": "#C97945",
    "darkness": "#424B58",
    "metal": "#8C9AA5",
    "dragon": "#B59A3C",
    "colorless": "#A7A9AC",
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
