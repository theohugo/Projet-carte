"""Les huit familles utilisées par les règles de Poké-Uno.

Les 18 types officiels restent affichés sur les cartes. Les familles ne servent
qu'à rendre les correspondances de jeu plus lisibles et plus fréquentes.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.models import PokemonCard


@dataclass(frozen=True, slots=True)
class TypeFamily:
    slug: str
    name_fr: str
    type_slugs: tuple[str, ...]
    accent_type: str

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name_fr": self.name_fr,
            "type_slugs": list(self.type_slugs),
            "accent_type": self.accent_type,
        }


TYPE_FAMILIES = (
    TypeFamily("ecosystem", "Écosystème toxique", ("bug", "grass", "poison"), "grass"),
    TypeFamily("shadows", "Royaume des ombres", ("ghost", "dark"), "ghost"),
    TypeFamily("forge", "Forge tellurique", ("ground", "rock", "steel"), "steel"),
    TypeFamily("arcane", "Arcane", ("psychic", "fairy"), "psychic"),
    TypeFamily("tides", "Marées gelées", ("water", "ice"), "water"),
    TypeFamily("skyfire", "Ciel ardent", ("fire", "flying"), "fire"),
    TypeFamily("instinct", "Instinct combatif", ("normal", "fighting"), "fighting"),
    TypeFamily("storm", "Tempête draconique", ("electric", "dragon"), "electric"),
)

FAMILY_BY_SLUG = {family.slug: family for family in TYPE_FAMILIES}
TYPE_TO_FAMILY = {type_slug: family.slug for family in TYPE_FAMILIES for type_slug in family.type_slugs}
FAMILY_CHOICES = tuple((family.slug, family.name_fr) for family in TYPE_FAMILIES)

if len(TYPE_TO_FAMILY) != 18:
    raise RuntimeError("Chaque type Pokémon doit appartenir à une seule famille de jeu.")


def get_family(family_slug: str | None) -> TypeFamily | None:
    if not isinstance(family_slug, str):
        return None
    return FAMILY_BY_SLUG.get(family_slug)


def family_slug_for_type(type_slug: str) -> str:
    try:
        return TYPE_TO_FAMILY[type_slug]
    except KeyError as exc:
        raise ValueError(f"Type Pokémon inconnu : {type_slug}.") from exc


def family_slugs_for_types(type_slugs: Iterable[str]) -> tuple[str, ...]:
    selected = {family_slug_for_type(type_slug) for type_slug in type_slugs}
    return tuple(family.slug for family in TYPE_FAMILIES if family.slug in selected)


def family_slugs_for_card(card: "PokemonCard") -> tuple[str, ...]:
    return family_slugs_for_types(pokemon_type.slug for pokemon_type in card.types)
