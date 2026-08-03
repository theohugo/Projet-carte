"""Construction déterministe d'une pioche équilibrée par types Pokémon.

Le catalogue actif est équilibré en amont. La pioche standard conserve deux
exemplaires de chaque espèce ; le repli glouton couvre les tailles personnalisées.
L'ordre de la pioche reste mélangé par le moteur.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from functools import partial

from game.models import PokemonCard

ACTION_CARD_COPIES = 2
BASE_NORMAL_CARD_COPIES = 1
MAX_NORMAL_CARD_COPIES = 4


def card_type_slugs(card: PokemonCard) -> tuple[str, ...]:
    """Renvoie les types d'une carte, sans requête si elle est select_related."""
    return tuple(
        pokemon_type.slug
        for pokemon_type in (card.primary_type, card.secondary_type)
        if pokemon_type is not None
    )


def count_cards_per_type(cards: Iterable[PokemonCard]) -> Counter[str]:
    """Compte chaque carte pour chacun de ses types (un double-type compte deux fois)."""
    counts: Counter[str] = Counter()
    for card in cards:
        counts.update(card_type_slugs(card))
    return counts


def _imbalance_score(type_counts: Counter[str], all_types: Sequence[str]) -> tuple[int, int]:
    """Mesure entière et stable : étendue, puis variance sans nombres flottants."""
    values = [type_counts[type_slug] for type_slug in all_types]
    total = sum(values)
    variance_numerator = len(values) * sum(value * value for value in values) - total * total
    return max(values) - min(values), variance_numerator


def _candidate_score(
    card: PokemonCard,
    *,
    type_counts: Counter[str],
    all_types: Sequence[str],
    rarest_types: set[str],
    prioritize_rarest: bool,
    copy_counts: dict[int, int],
) -> tuple[int, int, int, int, int]:
    projected_counts = type_counts.copy()
    card_types = card_type_slugs(card)
    projected_counts.update(card_types)
    spread, variance = _imbalance_score(projected_counts, all_types)
    rare_types_covered = len(rarest_types.intersection(card_types))
    return (
        -rare_types_covered if prioritize_rarest else 0,
        spread,
        variance,
        copy_counts[card.pk],
        card.pokedex_id,
    )


def allocate_balanced_copies(
    cards: Sequence[PokemonCard],
    *,
    target_size: int,
    max_normal_copies: int = MAX_NORMAL_CARD_COPIES,
) -> dict[int, int]:
    """Calcule la multiplicité de chaque Pokémon dans une pioche.

    Garanties :
    - chaque Pokémon du catalogue est conservé au moins une fois ;
    - chaque carte d'action reste exactement en deux exemplaires ;
    - seules les cartes normales reçoivent les copies d'équilibrage ;
    - aucune carte normale ne dépasse ``max_normal_copies`` ;
    - les égalités sont départagées par Pokédex ID, donc le résultat est stable.
    """
    ordered_cards = sorted(cards, key=lambda card: (card.pokedex_id, card.pk))
    if not ordered_cards:
        if target_size != 0:
            raise ValueError("Impossible de construire une pioche non vide sans Pokémon.")
        return {}

    if max_normal_copies < BASE_NORMAL_CARD_COPIES:
        raise ValueError("Le plafond des cartes normales doit être au moins égal à 1.")

    copy_counts = {
        card.pk: (ACTION_CARD_COPIES if card.action != PokemonCard.Action.NORMAL else BASE_NORMAL_CARD_COPIES)
        for card in ordered_cards
    }

    # Le catalogue de production est équilibré en amont (4 à 5 Pokémon par
    # type). Deux exemplaires par espèce préservent exactement cette répartition
    # et donnent 8 à 10 cartes de chacun des 18 types dans la pioche standard.
    uniform_size = len(ordered_cards) * ACTION_CARD_COPIES
    if target_size == uniform_size and max_normal_copies >= ACTION_CARD_COPIES:
        return {card.pk: ACTION_CARD_COPIES for card in ordered_cards}

    minimum_size = sum(copy_counts.values())
    maximum_size = sum(
        ACTION_CARD_COPIES if card.action != PokemonCard.Action.NORMAL else max_normal_copies
        for card in ordered_cards
    )
    if not minimum_size <= target_size <= maximum_size:
        raise ValueError(
            f"Taille de pioche impossible : {target_size} (attendu entre "
            f"{minimum_size} et {maximum_size})."
        )

    type_counts: Counter[str] = Counter()
    for card in ordered_cards:
        for _ in range(copy_counts[card.pk]):
            type_counts.update(card_type_slugs(card))
    all_types = sorted(type_counts)

    while sum(copy_counts.values()) < target_size:
        eligible_cards = [
            card
            for card in ordered_cards
            if card.action == PokemonCard.Action.NORMAL and copy_counts[card.pk] < max_normal_copies
        ]

        rarest_count = min(type_counts.values())
        rarest_types = {type_slug for type_slug, count in type_counts.items() if count == rarest_count}
        rare_candidates = [
            card for card in eligible_cards if rarest_types.intersection(card_type_slugs(card))
        ]
        candidates = rare_candidates or eligible_cards

        selected_card = min(
            candidates,
            key=partial(
                _candidate_score,
                type_counts=type_counts,
                all_types=all_types,
                rarest_types=rarest_types,
                prioritize_rarest=bool(rare_candidates),
                copy_counts=copy_counts,
            ),
        )
        copy_counts[selected_card.pk] += 1
        type_counts.update(card_type_slugs(selected_card))

    return copy_counts


def build_balanced_card_pool(
    cards: Sequence[PokemonCard],
    *,
    target_size: int,
    max_normal_copies: int = MAX_NORMAL_CARD_COPIES,
) -> list[PokemonCard]:
    """Développe les multiplicités calculées en liste de cartes physiques."""
    copy_counts = allocate_balanced_copies(
        cards,
        target_size=target_size,
        max_normal_copies=max_normal_copies,
    )
    return [
        card
        for card in sorted(cards, key=lambda item: (item.pokedex_id, item.pk))
        for _ in range(copy_counts[card.pk])
    ]
