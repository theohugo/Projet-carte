"""Boutique : acheter des boosters avec ses points et les ouvrir.

Le tirage vit côté serveur — un client ne voit ses cartes qu'une fois l'achat
enregistré et la collection mise à jour.

Deux façons de tirer, selon la saison. Le Set de Base tire une **espèce** et en
déduit la rareté (les évolutions finales sont rares, les légendaires le sont
plus encore). La série 151 tire une **impression** : la rareté est celle de la
carte réelle, de la commune à la Rare Or, et deux impressions d'un même Pokémon
sont deux cartes à collectionner.

Deux façons d'ouvrir, aussi : payer en points (``open_booster``) ou consommer
un ticket gagné en quête (``open_ticket``). Le tirage et la mise à jour de la
collection sont les mêmes dans les deux cas.
"""

import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from game.card_prints import get_print, prints_of
from game.models import BoosterOpening, BoosterTicket, CollectionCard, PokemonCard, Profile
from game.pokemon_names import GEN_ONE_MAX_POKEDEX_ID, bilingual_text, localized_pokemon_name
from game.rarities import (
    COMMUNE,
    DOUBLE_RARE,
    HYPER_RARE,
    ILLUSTRATION_RARE,
    ILLUSTRATION_SPECIALE,
    LEGENDAIRE,
    PEU_COMMUNE,
    RARE,
    ULTRA_RARE,
    get_rarity,
)
from game.rarities import as_dict as rarity_payload
from game.seasons import SEASON_151, SEASON_BASE, has_prints
from game.tcg_card_images import get_tcg_image_url

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
    label_en: str
    description: str
    description_en: str
    price: int
    card_count: int
    # Probabilité de chaque rareté pour une carte ordinaire du booster.
    odds: tuple[tuple[str, float], ...]
    season: int = SEASON_BASE
    guaranteed: str | None = None

    @property
    def display_label(self):
        return bilingual_text(self.label, self.label_en)

    @property
    def display_description(self):
        return bilingual_text(self.description, self.description_en)


BOOSTERS = (
    Booster(
        key="base",
        label="Booster Set de Base",
        label_en="Base Set Booster",
        description="Cinq cartes de la première édition. Une rare de temps en temps.",
        description_en="Five first-edition cards, with an occasional Rare.",
        price=150,
        card_count=5,
        odds=((COMMUNE, 0.82), (RARE, 0.15), (LEGENDAIRE, 0.03)),
        season=SEASON_BASE,
    ),
    Booster(
        key="premium",
        label="Booster Premium",
        label_en="Premium Booster",
        description="Cinq cartes, dont une rare garantie et de vraies chances de légendaire.",
        description_en="Five cards, including a guaranteed Rare and a real chance of a Legendary.",
        price=400,
        card_count=5,
        odds=((COMMUNE, 0.62), (RARE, 0.28), (LEGENDAIRE, 0.10)),
        season=SEASON_BASE,
        guaranteed=RARE,
    ),
    Booster(
        key="s151",
        label="Booster 151",
        label_en="151 Booster",
        description="Cinq cartes du set 151, avec ses huit raretés — jusqu'à la Rare Or.",
        description_en="Five cards from the 151 set across all eight rarities, up to Hyper Rare.",
        price=220,
        card_count=5,
        odds=(
            (COMMUNE, 0.50),
            (PEU_COMMUNE, 0.31),
            (RARE, 0.12),
            (DOUBLE_RARE, 0.035),
            (ILLUSTRATION_RARE, 0.02),
            (ULTRA_RARE, 0.011),
            (ILLUSTRATION_SPECIALE, 0.003),
            (HYPER_RARE, 0.001),
        ),
        season=SEASON_151,
    ),
    Booster(
        key="s151_ultra",
        label="Booster 151 Ultra",
        label_en="151 Ultra Booster",
        description="Cinq cartes du set 151, une rare garantie et les meilleures chances d'illustration.",
        description_en="Five 151 cards, a guaranteed Rare and the best Illustration Rare odds.",
        price=520,
        card_count=5,
        odds=(
            (COMMUNE, 0.30),
            (PEU_COMMUNE, 0.32),
            (RARE, 0.22),
            (DOUBLE_RARE, 0.08),
            (ILLUSTRATION_RARE, 0.05),
            (ULTRA_RARE, 0.02),
            (ILLUSTRATION_SPECIALE, 0.008),
            (HYPER_RARE, 0.002),
        ),
        season=SEASON_151,
        guaranteed=RARE,
    ),
)

BOOSTERS_BY_KEY = {booster.key: booster for booster in BOOSTERS}


class ShopError(Exception):
    """Achat impossible."""


# ── Saison à une carte par espèce ────────────────────────────────────────


def rarity_of(pokemon_card: PokemonCard, season: int = SEASON_BASE) -> str:
    """La rareté d'une espèce dans une saison sans impressions."""

    if pokemon_card.is_legendary:
        return LEGENDAIRE
    if pokemon_card.pokedex_id in RARE_POKEDEX_IDS:
        return RARE
    return COMMUNE


def _species_pools() -> dict[str, list[PokemonCard]]:
    pools: dict[str, list[PokemonCard]] = {COMMUNE: [], RARE: [], LEGENDAIRE: []}
    for card in PokemonCard.objects.filter(pokedex_id__lte=GEN_ONE_MAX_POKEDEX_ID):
        pools[rarity_of(card)].append(card)
    return pools


# ── Saison à impressions ─────────────────────────────────────────────────


def _print_pools(season: int) -> dict[str, list]:
    pools: dict[str, list] = {}
    for card in prints_of(season):
        pools.setdefault(card.rarity, []).append(card)
    return pools


def _draw_rarity(booster: Booster, rng) -> str:
    roll = rng.random()
    cumulative = 0.0
    for rarity, odds in booster.odds:
        cumulative += odds
        if roll < cumulative:
            return rarity
    return COMMUNE


def _fallback(pools: dict[str, list], wanted: str):
    """Le meilleur repli quand une rareté n'a rien à offrir dans ce catalogue.

    On redescend l'échelle plutôt que de vider le booster : un catalogue
    incomplet (tests, seed partiel) ne doit jamais casser une ouverture.
    """

    if pools.get(wanted):
        return pools[wanted]
    ordered = sorted(pools.items(), key=lambda item: get_rarity(item[0]).rank)
    for _, pool in ordered:
        if pool:
            return pool
    return []


def draw_cards(booster: Booster, rng=None) -> list:
    """Tire le contenu d'un booster, rareté garantie comprise.

    Renvoie des espèces (``PokemonCard``) ou des impressions (``CardPrint``)
    selon la saison du booster.
    """

    rng = rng or random
    pools = _print_pools(booster.season) if has_prints(booster.season) else _species_pools()
    if not any(pools.values()):
        raise ShopError(
            bilingual_text(
                "Le catalogue ne contient aucune carte pour cette saison.",
                "The catalogue has no cards for this season.",
            )
        )

    rarities = [_draw_rarity(booster, rng) for _ in range(booster.card_count)]
    if booster.guaranteed and pools.get(booster.guaranteed):
        best = max(get_rarity(rarity).rank for rarity in rarities)
        if best < get_rarity(booster.guaranteed).rank:
            # La carte garantie remplace la dernière tirée : le booster garde sa taille.
            rarities[-1] = booster.guaranteed

    return [rng.choice(_fallback(pools, rarity)) for rarity in rarities]


# ── Ouverture ────────────────────────────────────────────────────────────


def _describe(drawn, season: int) -> dict:
    """Ce que le navigateur reçoit pour une carte tirée."""

    if has_prints(season):
        species = PokemonCard.objects.filter(pokedex_id=drawn.dex_id).first()
        return {
            "variant": drawn.variant,
            "pokedex_id": drawn.dex_id,
            "name": localized_pokemon_name(species) if species else drawn.name_fr,
            "image_url": drawn.image,
        } | rarity_payload(drawn.rarity)

    return {
        "variant": "",
        "pokedex_id": drawn.pokedex_id,
        "name": localized_pokemon_name(drawn),
        "image_url": get_tcg_image_url(drawn.pokedex_id, season),
        "sprite_url": drawn.sprite_url,
    } | rarity_payload(rarity_of(drawn, season))


def _species_of(drawn, season: int) -> PokemonCard | None:
    """L'espèce du catalogue derrière une carte tirée."""

    if not has_prints(season):
        return drawn
    return PokemonCard.objects.filter(pokedex_id=drawn.dex_id).first()


def _grant(user, booster: Booster, price: int, rng=None) -> dict:
    """Tire le booster, l'archive et range les cartes dans la collection.

    Ni le débit ni la consommation du ticket ne sont faits ici : l'appelant
    choisit comment le booster a été payé.
    """

    drawn = draw_cards(booster, rng)
    season = booster.season

    opening = BoosterOpening.objects.create(
        user=user,
        booster_key=booster.key,
        season=season,
        price=price,
    )

    payload = []
    species_ids = []
    for card in drawn:
        entry = _describe(card, season)
        species = _species_of(card, season)
        if species is None:
            # Une impression sans espèce au catalogue reste montrée au joueur,
            # mais ne peut pas entrer en collection.
            payload.append(entry | {"is_new": False})
            continue

        species_ids.append(species.pk)
        collected, created = CollectionCard.objects.get_or_create(
            user=user,
            pokemon_card=species,
            season=season,
            variant=entry["variant"],
            defaults={"rarity": entry["rarity"]},
        )
        if not created:
            CollectionCard.objects.filter(pk=collected.pk).update(copies=F("copies") + 1)
        payload.append(entry | {"is_new": created, "sprite_url": entry.get("sprite_url", species.sprite_url)})

    opening.cards.set(species_ids)

    return {"booster": booster.display_label, "season": season, "cards": payload}


# Lots proposés en boutique. Ouvrir dix boosters d'un coup évite dix
# allers-retours, mais il faut une borne : le tirage se fait en une transaction.
BATCH_SIZES = (1, 5, 10)


def clean_quantity(value) -> int:
    """Le nombre de boosters demandé, ramené à un lot proposé."""

    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return 1
    return quantity if quantity in BATCH_SIZES else 1


@transaction.atomic
def open_booster(user, booster_key: str, rng=None, quantity: int = 1) -> dict:
    """Débite les points, tire les cartes et les ajoute à la collection.

    ``quantity`` ouvre plusieurs boosters d'affilée : un seul débit, une seule
    transaction, mais une archive par booster.
    """

    booster = BOOSTERS_BY_KEY.get(booster_key)
    if booster is None:
        raise ShopError(bilingual_text("Ce booster n'existe pas.", "This booster does not exist."))

    quantity = clean_quantity(quantity)
    total = booster.price * quantity

    profile = Profile.objects.select_for_update().get(user=user)
    if profile.points < total:
        missing = total - profile.points
        if quantity > 1:
            raise ShopError(
                bilingual_text(
                    f"Il te manque {missing} points pour ces {quantity} boosters.",
                    f"You need {missing} more points for these {quantity} boosters.",
                )
            )
        raise ShopError(
            bilingual_text(
                f"Il te manque {missing} points pour ce booster.",
                f"You need {missing} more points for this booster.",
            )
        )

    results = [_grant(user, booster, booster.price, rng) for _ in range(quantity)]
    Profile.objects.filter(pk=profile.pk).update(points=F("points") - total)

    profile.refresh_from_db(fields=["points"])
    return {
        "booster": booster.display_label,
        "season": booster.season,
        "quantity": quantity,
        "cards": [card for result in results for card in result["cards"]],
        "points_left": profile.points,
        "tickets_left": pending_tickets(user).count(),
    }


@transaction.atomic
def open_ticket(user, ticket_id: int, rng=None) -> dict:
    """Ouvre un booster gagné en quête. Gratuit, mais le ticket est consommé."""

    ticket = (
        BoosterTicket.objects.select_for_update()
        .filter(user=user, pk=ticket_id, opened_at__isnull=True)
        .first()
    )
    if ticket is None:
        raise ShopError(
            bilingual_text(
                "Ce booster de quête n'est plus disponible.",
                "This quest booster is no longer available.",
            )
        )

    booster = BOOSTERS_BY_KEY.get(ticket.booster_key)
    if booster is None:
        raise ShopError(bilingual_text("Ce booster n'existe pas.", "This booster does not exist."))

    result = _grant(user, booster, 0, rng)
    ticket.opened_at = timezone.now()
    ticket.save(update_fields=["opened_at"])

    return result | {
        "quantity": 1,
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


def collection_rarity(collected: CollectionCard) -> str:
    """La rareté d'une carte possédée, recalculée si elle n'a pas été stockée."""

    if collected.rarity:
        return collected.rarity
    if has_prints(collected.season):
        card = get_print(collected.season, collected.variant)
        return card.rarity if card else COMMUNE
    return rarity_of(collected.pokemon_card, collected.season)
