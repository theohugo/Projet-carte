"""Référentiel des 18 types Pokémon des jeux vidéo.

Poké-Uno se joue avec les types authentiques : un Pokémon peut en porter deux,
ce qui en fait une passerelle entre deux couleurs de la partie. Chaque partie
tire ``GAME_TYPE_COUNT`` types au sort ; ce module ne porte que les métadonnées
d'affichage stables (ordre, libellé, couleur), les types eux-mêmes restant des
lignes :class:`~game.models.PokemonType` alimentées par le seed.
"""

from dataclasses import dataclass

# Nombre de types tirés au sort au démarrage d'une partie.
GAME_TYPE_COUNT = 4
# Espèces retenues pour chacun de ces types.
SPECIES_PER_TYPE = 20


@dataclass(frozen=True, slots=True)
class PokemonTypeInfo:
    """Métadonnées d'affichage d'un type source."""

    slug: str
    name_fr: str
    color: str

    def as_dict(self) -> dict[str, str]:
        return {"slug": self.slug, "name_fr": self.name_fr, "color": self.color}


# Couleurs officieuses mais universelles des types, retenues telles quelles pour
# que les joueurs reconnaissent immédiatement une couleur de type.
POKEMON_TYPES = (
    PokemonTypeInfo("normal", "Normal", "#9fa19f"),
    PokemonTypeInfo("fire", "Feu", "#e8752f"),
    PokemonTypeInfo("water", "Eau", "#3d90d8"),
    PokemonTypeInfo("electric", "Électrik", "#e5c22b"),
    PokemonTypeInfo("grass", "Plante", "#63bb5b"),
    PokemonTypeInfo("ice", "Glace", "#4fd0c5"),
    PokemonTypeInfo("fighting", "Combat", "#ce4069"),
    PokemonTypeInfo("poison", "Poison", "#a862c8"),
    PokemonTypeInfo("ground", "Sol", "#d3893f"),
    PokemonTypeInfo("flying", "Vol", "#8fa8dd"),
    PokemonTypeInfo("psychic", "Psy", "#f66f88"),
    PokemonTypeInfo("bug", "Insecte", "#91c12f"),
    PokemonTypeInfo("rock", "Roche", "#c7b78b"),
    PokemonTypeInfo("ghost", "Spectre", "#7b62a3"),
    PokemonTypeInfo("dragon", "Dragon", "#0c69c8"),
    PokemonTypeInfo("dark", "Ténèbres", "#5a5465"),
    PokemonTypeInfo("steel", "Acier", "#5a8ea1"),
    PokemonTypeInfo("fairy", "Fée", "#ec8fe6"),
)

POKEMON_TYPE_BY_SLUG = {pokemon_type.slug: pokemon_type for pokemon_type in POKEMON_TYPES}
POKEMON_TYPE_SLUGS = tuple(pokemon_type.slug for pokemon_type in POKEMON_TYPES)


def get_pokemon_type(slug) -> PokemonTypeInfo | None:
    """Métadonnées d'un type, ou ``None`` si le slug est inconnu."""

    if not isinstance(slug, str):
        return None
    return POKEMON_TYPE_BY_SLUG.get(slug)


def type_color(slug) -> str:
    """Couleur d'un type, avec un gris neutre pour les valeurs inattendues."""

    pokemon_type = get_pokemon_type(slug)
    return pokemon_type.color if pokemon_type else "#9fa19f"
