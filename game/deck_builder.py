"""Tirage de la pioche d'une partie de Poké-Uno.

Chaque partie tire ``GAME_TYPE_COUNT`` types parmi les 18 types des jeux vidéo,
puis ``SPECIES_PER_TYPE`` espèces pour chacun de ces types. Un Pokémon à double
type peut être retenu au titre de deux types de la partie : il devient alors une
passerelle entre deux couleurs, ce qui est le cœur du jeu.

L'équilibre ne vient donc plus d'un catalogue figé mais du tirage lui-même :
chaque type de la partie est garanti par le même nombre d'espèces.
"""

from collections import defaultdict
from collections.abc import Sequence

from game.models import PokemonCard
from game.pokemon_types import GAME_TYPE_COUNT, POKEMON_TYPE_SLUGS, SPECIES_PER_TYPE


class DeckDraftError(Exception):
    """Le catalogue ne permet pas de composer une pioche."""


def species_type_slugs(card: PokemonCard) -> tuple[str, ...]:
    """Types d'une espèce, sans requête si elle est chargée en select_related."""

    return tuple(
        pokemon_type.slug
        for pokemon_type in (card.primary_type, card.secondary_type)
        if pokemon_type is not None
    )


def species_by_type(species: Sequence[PokemonCard]) -> dict[str, list[PokemonCard]]:
    """Regroupe les espèces par type ; un double type apparaît dans deux groupes."""

    pools: dict[str, list[PokemonCard]] = defaultdict(list)
    for card in species:
        for slug in species_type_slugs(card):
            pools[slug].append(card)
    return pools


def draw_game_types(
    species: Sequence[PokemonCard],
    rng,
    *,
    count: int = GAME_TYPE_COUNT,
    species_per_type: int = SPECIES_PER_TYPE,
) -> list[str]:
    """Tire au sort les types de la partie parmi ceux assez fournis."""

    pools = species_by_type(species)
    eligible = [slug for slug in POKEMON_TYPE_SLUGS if len(pools.get(slug, [])) >= species_per_type]
    if len(eligible) < count:
        raise DeckDraftError(
            f"Il faut au moins {count} types comptant {species_per_type} espèces au catalogue "
            f"(seulement {len(eligible)} disponibles)."
        )
    return rng.sample(eligible, count)


def select_species(
    species: Sequence[PokemonCard],
    type_slugs: Sequence[str],
    rng,
    *,
    species_per_type: int = SPECIES_PER_TYPE,
) -> list[PokemonCard]:
    """Tire ``species_per_type`` espèces pour chacun des types de la partie.

    Une espèce éligible à deux des types tirés n'est retenue qu'une fois, mais
    compte bien pour chacun d'eux : chaque type reste représenté par le nombre
    d'espèces demandé.
    """

    pools = species_by_type(species)
    selected: dict[int, PokemonCard] = {}
    for slug in type_slugs:
        pool = sorted(pools.get(slug, []), key=lambda card: card.pokedex_id)
        if len(pool) < species_per_type:
            raise DeckDraftError(f"Le type {slug} ne compte pas {species_per_type} espèces au catalogue.")
        for card in rng.sample(pool, species_per_type):
            selected[card.pk] = card
    return sorted(selected.values(), key=lambda card: card.pokedex_id)
