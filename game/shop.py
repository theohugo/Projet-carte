"""Boutique : acheter des boosters avec ses points et les ouvrir.

Le tirage vit côté serveur — un client ne voit ses cartes qu'une fois l'achat
enregistré et la collection mise à jour. Les raretés reprennent l'esprit du Set
de Base : beaucoup de communes, quelques rares, et les légendaires en éclat.
"""

import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F

from game.models import BoosterOpening, CollectionCard, PokemonCard, Profile
from game.pokemon_names import GEN_ONE_MAX_POKEDEX_ID

COMMUNE = "COMMUNE"
RARE = "RARE"
LEGENDAIRE = "LEGENDAIRE"

RARITY_LABELS = {
    COMMUNE: "Commune",
    RARE: "Rare",
    LEGENDAIRE: "Légendaire",
}

# Évolutions finales et vedettes du Set de Base : ce sont les cartes qu'on
# espère en ouvrant un booster.
# fmt: off
RARE_POKEDEX_IDS = frozenset((
    3, 6, 9, 12, 15, 18, 26, 31, 34, 36, 38, 40, 45, 51, 53, 55, 57, 59, 62, 65, 68, 71, 76, 78, 80, 82,
    85, 87, 89, 91, 94, 97, 101, 103, 105, 106, 107, 110, 112, 113, 115, 117, 119, 121, 122, 123, 125,
    126, 127, 130, 131, 134, 135, 136, 139, 141, 142, 143
))
# fmt: on


@dataclass(frozen=True, slots=True)
class Booster:
    key: str
    label: str
    description: str
    price: int
    card_count: int
    # Probabilité de chaque rareté pour une carte ordinaire du booster.
    odds: tuple[tuple[str, float], ...]
    guaranteed: str | None = None


BOOSTERS = (
    Booster(
        key="base",
        label="Booster Set de Base",
        description="Cinq cartes de la première édition. Une rare de temps en temps.",
        price=150,
        card_count=5,
        odds=((COMMUNE, 0.82), (RARE, 0.15), (LEGENDAIRE, 0.03)),
    ),
    Booster(
        key="premium",
        label="Booster Premium",
        description="Cinq cartes, dont une rare garantie et de vraies chances de légendaire.",
        price=400,
        card_count=5,
        odds=((COMMUNE, 0.62), (RARE, 0.28), (LEGENDAIRE, 0.10)),
        guaranteed=RARE,
    ),
)

BOOSTERS_BY_KEY = {booster.key: booster for booster in BOOSTERS}


class ShopError(Exception):
    """Achat impossible."""


def rarity_of(pokemon_card: PokemonCard) -> str:
    if pokemon_card.is_legendary:
        return LEGENDAIRE
    if pokemon_card.pokedex_id in RARE_POKEDEX_IDS:
        return RARE
    return COMMUNE


def _pool_by_rarity() -> dict[str, list[PokemonCard]]:
    cards = PokemonCard.objects.filter(pokedex_id__lte=GEN_ONE_MAX_POKEDEX_ID)
    pools: dict[str, list[PokemonCard]] = {COMMUNE: [], RARE: [], LEGENDAIRE: []}
    for card in cards:
        pools[rarity_of(card)].append(card)
    return pools


def _draw_rarity(booster: Booster, rng) -> str:
    roll = rng.random()
    cumulative = 0.0
    for rarity, odds in booster.odds:
        cumulative += odds
        if roll < cumulative:
            return rarity
    return COMMUNE


def draw_cards(booster: Booster, rng=None) -> list[PokemonCard]:
    """Tire le contenu d'un booster, rareté garantie comprise."""

    rng = rng or random
    pools = _pool_by_rarity()
    if not any(pools.values()):
        raise ShopError("Le catalogue ne contient aucune carte de la première génération.")

    rarities = [_draw_rarity(booster, rng) for _ in range(booster.card_count)]
    if booster.guaranteed and booster.guaranteed not in rarities and pools[booster.guaranteed]:
        # La carte garantie remplace la dernière tirée : le booster garde sa taille.
        rarities[-1] = booster.guaranteed

    cards = []
    for rarity in rarities:
        pool = pools[rarity] or pools[COMMUNE] or pools[RARE] or pools[LEGENDAIRE]
        cards.append(rng.choice(pool))
    return cards


@transaction.atomic
def open_booster(user, booster_key: str, rng=None) -> dict:
    """Débite les points, tire les cartes et les ajoute à la collection."""

    booster = BOOSTERS_BY_KEY.get(booster_key)
    if booster is None:
        raise ShopError("Ce booster n'existe pas.")

    profile = Profile.objects.select_for_update().get(user=user)
    if profile.points < booster.price:
        raise ShopError(f"Il te manque {booster.price - profile.points} points pour ce booster.")

    cards = draw_cards(booster, rng)
    Profile.objects.filter(pk=profile.pk).update(points=F("points") - booster.price)

    opening = BoosterOpening.objects.create(user=user, booster_key=booster.key, price=booster.price)
    opening.cards.set(cards)

    payload = []
    for card in cards:
        collected, created = CollectionCard.objects.get_or_create(user=user, pokemon_card=card)
        if not created:
            CollectionCard.objects.filter(pk=collected.pk).update(copies=F("copies") + 1)
        payload.append(
            {
                "pokedex_id": card.pokedex_id,
                "name": card.name_fr,
                "rarity": rarity_of(card),
                "rarity_label": RARITY_LABELS[rarity_of(card)],
                "is_new": created,
                "sprite_url": card.sprite_url,
            }
        )

    profile.refresh_from_db(fields=["points"])
    return {"booster": booster.label, "cards": payload, "points_left": profile.points}
