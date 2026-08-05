"""Boutique : acheter des boosters avec ses points et les ouvrir.

Le tirage vit côté serveur — un client ne voit ses cartes qu'une fois l'achat
enregistré et la collection mise à jour. Les raretés reprennent l'esprit du Set
de Base : beaucoup de communes, quelques rares, et les légendaires en éclat.
La saison 2 ajoute une rareté au-dessus, la carte *ex*.

Deux façons d'ouvrir un booster : le payer en points (``open_booster``) ou
consommer un ticket gagné en quête (``open_ticket``). Le tirage et la mise à
jour de la collection sont les mêmes dans les deux cas.
"""

import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from game.models import BoosterOpening, BoosterTicket, CollectionCard, PokemonCard, Profile
from game.pokemon_names import GEN_ONE_MAX_POKEDEX_ID
from game.seasons import DEFAULT_SEASON, EX_POKEDEX_IDS, SEASON_151, SEASON_BASE, get_season

COMMUNE = "COMMUNE"
RARE = "RARE"
LEGENDAIRE = "LEGENDAIRE"
EX = "EX"

RARITY_LABELS = {
    COMMUNE: "Commune",
    RARE: "Rare",
    LEGENDAIRE: "Légendaire",
    EX: "Carte ex",
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
    season: int = SEASON_BASE
    guaranteed: str | None = None


BOOSTERS = (
    Booster(
        key="base",
        label="Booster Set de Base",
        description="Cinq cartes de la première édition. Une rare de temps en temps.",
        price=150,
        card_count=5,
        odds=((COMMUNE, 0.82), (RARE, 0.15), (LEGENDAIRE, 0.03)),
        season=SEASON_BASE,
    ),
    Booster(
        key="premium",
        label="Booster Premium",
        description="Cinq cartes, dont une rare garantie et de vraies chances de légendaire.",
        price=400,
        card_count=5,
        odds=((COMMUNE, 0.62), (RARE, 0.28), (LEGENDAIRE, 0.10)),
        season=SEASON_BASE,
        guaranteed=RARE,
    ),
    Booster(
        key="s151",
        label="Booster 151",
        description="Cinq cartes de la série 151, et la chance d'y trouver une carte ex.",
        price=220,
        card_count=5,
        odds=((COMMUNE, 0.74), (RARE, 0.20), (LEGENDAIRE, 0.04), (EX, 0.02)),
        season=SEASON_151,
    ),
    Booster(
        key="s151_ultra",
        label="Booster 151 Ultra",
        description="Cinq cartes de la série 151, une rare garantie et une carte ex sur cinq ouvertures.",
        price=520,
        card_count=5,
        odds=((COMMUNE, 0.52), (RARE, 0.32), (LEGENDAIRE, 0.10), (EX, 0.06)),
        season=SEASON_151,
        guaranteed=RARE,
    ),
)

BOOSTERS_BY_KEY = {booster.key: booster for booster in BOOSTERS}


class ShopError(Exception):
    """Achat impossible."""


def rarity_of(pokemon_card: PokemonCard, season: int = DEFAULT_SEASON) -> str:
    """La rareté de cette espèce dans cette édition.

    Un même Pokémon peut changer de rang d'une saison à l'autre : Dracaufeu est
    une rare du Set de Base et une carte ex de la série 151.
    """

    if get_season(season).has_ex and pokemon_card.pokedex_id in EX_POKEDEX_IDS:
        return EX
    if pokemon_card.is_legendary:
        return LEGENDAIRE
    if pokemon_card.pokedex_id in RARE_POKEDEX_IDS:
        return RARE
    return COMMUNE


def _pool_by_rarity(season: int) -> dict[str, list[PokemonCard]]:
    cards = PokemonCard.objects.filter(pokedex_id__lte=GEN_ONE_MAX_POKEDEX_ID)
    pools: dict[str, list[PokemonCard]] = {COMMUNE: [], RARE: [], LEGENDAIRE: [], EX: []}
    for card in cards:
        pools[rarity_of(card, season)].append(card)
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
    pools = _pool_by_rarity(booster.season)
    if not any(pools.values()):
        raise ShopError("Le catalogue ne contient aucune carte de la première génération.")

    rarities = [_draw_rarity(booster, rng) for _ in range(booster.card_count)]
    if booster.guaranteed and booster.guaranteed not in rarities and pools[booster.guaranteed]:
        # La carte garantie remplace la dernière tirée : le booster garde sa taille.
        rarities[-1] = booster.guaranteed

    cards = []
    for rarity in rarities:
        pool = pools[rarity] or pools[COMMUNE] or pools[RARE] or pools[LEGENDAIRE] or pools[EX]
        cards.append(rng.choice(pool))
    return cards


def _grant(user, booster: Booster, price: int, rng=None) -> dict:
    """Tire le booster, l'archive et range les cartes dans la collection.

    Ni le débit ni la consommation du ticket ne sont faits ici : l'appelant
    choisit comment le booster a été payé.
    """

    cards = draw_cards(booster, rng)

    opening = BoosterOpening.objects.create(
        user=user,
        booster_key=booster.key,
        season=booster.season,
        price=price,
    )
    opening.cards.set(cards)

    payload = []
    for card in cards:
        rarity = rarity_of(card, booster.season)
        collected, created = CollectionCard.objects.get_or_create(
            user=user,
            pokemon_card=card,
            season=booster.season,
        )
        if not created:
            CollectionCard.objects.filter(pk=collected.pk).update(copies=F("copies") + 1)
        payload.append(
            {
                "pokedex_id": card.pokedex_id,
                "name": card.name_fr,
                "rarity": rarity,
                "rarity_label": RARITY_LABELS[rarity],
                "is_new": created,
                "sprite_url": card.sprite_url,
            }
        )

    return {
        "booster": booster.label,
        "season": booster.season,
        "cards": payload,
    }


@transaction.atomic
def open_booster(user, booster_key: str, rng=None) -> dict:
    """Débite les points, tire les cartes et les ajoute à la collection."""

    booster = BOOSTERS_BY_KEY.get(booster_key)
    if booster is None:
        raise ShopError("Ce booster n'existe pas.")

    profile = Profile.objects.select_for_update().get(user=user)
    if profile.points < booster.price:
        raise ShopError(f"Il te manque {booster.price - profile.points} points pour ce booster.")

    result = _grant(user, booster, booster.price, rng)
    Profile.objects.filter(pk=profile.pk).update(points=F("points") - booster.price)

    profile.refresh_from_db(fields=["points"])
    return result | {"points_left": profile.points, "tickets_left": pending_tickets(user).count()}


@transaction.atomic
def open_ticket(user, ticket_id: int, rng=None) -> dict:
    """Ouvre un booster gagné en quête. Gratuit, mais le ticket est consommé."""

    ticket = (
        BoosterTicket.objects.select_for_update()
        .filter(user=user, pk=ticket_id, opened_at__isnull=True)
        .first()
    )
    if ticket is None:
        raise ShopError("Ce booster de quête n'est plus disponible.")

    booster = BOOSTERS_BY_KEY.get(ticket.booster_key)
    if booster is None:
        raise ShopError("Ce booster n'existe pas.")

    result = _grant(user, booster, 0, rng)
    ticket.opened_at = timezone.now()
    ticket.save(update_fields=["opened_at"])

    return result | {
        "points_left": Profile.objects.get(user=user).points,
        "tickets_left": pending_tickets(user).count(),
    }


def pending_tickets(user):
    """Les boosters gagnés et pas encore ouverts, du plus ancien au plus récent."""

    return BoosterTicket.objects.filter(user=user, opened_at__isnull=True)


def grant_ticket(user, booster_key: str, source: str = "") -> BoosterTicket | None:
    """Offre un booster à ouvrir plus tard. Ignore une clé inconnue."""

    if booster_key not in BOOSTERS_BY_KEY:
        return None
    return BoosterTicket.objects.create(user=user, booster_key=booster_key, source=source)
