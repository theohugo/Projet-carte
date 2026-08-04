import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from game.card_actions import action_for_pokedex_id
from game.management.commands._pokedex_selection import (
    ALL_TCG_TYPE_SLUGS,
    ALL_TYPE_SLUGS,
    CURATED_POKEDEX_IDS,
    TCG_TYPE_BY_POKEDEX_ID,
)
from game.models import PokemonCard, PokemonType
from game.tcg_types import get_tcg_type, tcg_type_slug_for_source_type

DEFAULT_FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "pokemon_cards.json"
POKEAPI_BASE = "https://pokeapi.co/api/v2"
# PokeAPI n'impose pas de quota, mais reste un service gratuit : la
# parallélisation est modérée pour ne pas le marteler.
CATALOGUE_WORKERS = 8


class Command(BaseCommand):
    help = (
        "Peuple le catalogue de cartes Pokémon. Par défaut, charge le fixture JSON "
        "committé (aucun accès réseau). Avec --from-api, régénère ce fixture en "
        "interrogeant PokeAPI."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-api",
            action="store_true",
            help="Régénère le fixture en interrogeant PokeAPI (nécessite un accès réseau).",
        )
        parser.add_argument(
            "--catalogue-limit",
            type=int,
            default=0,
            help=(
                "Avec --from-api, limite le nombre d'espèces hors pioche récupérées "
                "(0 = tout le Pokédex). Utile pour un essai rapide."
            ),
        )
        parser.add_argument(
            "--fixture",
            type=Path,
            default=DEFAULT_FIXTURE,
            help="Chemin du fixture JSON à charger (ou à écrire avec --from-api).",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Supprime les PokemonCard/PokemonType existants avant de charger.",
        )

    def handle(self, *args, **options):
        fixture_path = options["fixture"]

        if options["from_api"]:
            data = self._fetch_from_api(options["catalogue_limit"])
            fixture_path.parent.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Fixture régénéré : {fixture_path}"))
        else:
            if not fixture_path.exists():
                raise CommandError(
                    f"Fixture introuvable : {fixture_path}. Lance d'abord "
                    "`manage.py seed_pokemon_cards --from-api`."
                )
            data = json.loads(fixture_path.read_text(encoding="utf-8"))

        if options["flush"]:
            PokemonCard.objects.all().delete()
            PokemonType.objects.all().delete()

        self._load_into_db(data)
        self._print_coverage_report(data)

    @transaction.atomic
    def _load_into_db(self, data):
        catalogue = data.get("catalogue", [])
        selected_pokedex_ids = {card["pokedex_id"] for card in data["cards"]}
        # Une ancienne espèce peut encore être référencée par une partie. Elle
        # reste consultable dans l'historique, mais sort des nouvelles pioches.
        PokemonCard.objects.exclude(pokedex_id__in=selected_pokedex_ids).update(in_current_deck=False)

        types_by_slug = {}
        for t in data["types"]:
            obj, _ = PokemonType.objects.update_or_create(
                slug=t["slug"],
                defaults={"name_fr": t["name_fr"], "name_en": t["name_en"]},
            )
            types_by_slug[t["slug"]] = obj

        card_field_names = {field.name for field in PokemonCard._meta.concrete_fields}
        supports_tcg_type = "tcg_type" in card_field_names

        # La pioche Poké-Uno (`in_current_deck`) reste la sélection éditoriale ;
        # le reste du catalogue n'existe que pour le tirage du Qui est-ce ?.
        for card, in_current_deck in [(c, True) for c in data["cards"]] + [(c, False) for c in catalogue]:
            defaults = {
                "slug": card["slug"],
                "name_fr": card["name_fr"],
                "name_en": card["name_en"],
                "primary_type": types_by_slug[card["primary_type"]],
                "secondary_type": (
                    types_by_slug[card["secondary_type"]] if card.get("secondary_type") else None
                ),
                "sprite_url": card["sprite_url"],
                "is_legendary": card["is_legendary"],
                "action": card.get("action", action_for_pokedex_id(card["pokedex_id"])),
                "in_current_deck": in_current_deck,
            }
            if supports_tcg_type:
                defaults["tcg_type"] = self._tcg_type_for_card(card)

            PokemonCard.objects.update_or_create(
                pokedex_id=card["pokedex_id"],
                defaults=defaults,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(data['cards'])} cartes de la pioche et {len(catalogue)} espèces "
                "supplémentaires au catalogue."
            )
        )

    def _print_coverage_report(self, data):
        covered_types = set()
        tcg_type_counts = Counter()
        legendary_count = 0
        for c in data["cards"]:
            covered_types.add(c["primary_type"])
            if c.get("secondary_type"):
                covered_types.add(c["secondary_type"])
            tcg_type_counts[self._tcg_type_for_card(c)] += 1
            if c["is_legendary"]:
                legendary_count += 1

        missing = set(ALL_TYPE_SLUGS) - covered_types
        self.stdout.write(f"Types couverts : {len(covered_types)}/{len(ALL_TYPE_SLUGS)}")
        if missing:
            self.stdout.write(self.style.WARNING(f"Types manquants : {sorted(missing)}"))
        missing_tcg_types = set(ALL_TCG_TYPE_SLUGS) - set(tcg_type_counts)
        self.stdout.write(f"Types JCC couverts : {len(tcg_type_counts)}/{len(ALL_TCG_TYPE_SLUGS)}")
        if missing_tcg_types:
            self.stdout.write(self.style.WARNING(f"Types JCC manquants : {sorted(missing_tcg_types)}"))
        distribution = ", ".join(f"{slug}={tcg_type_counts.get(slug, 0)}" for slug in ALL_TCG_TYPE_SLUGS)
        self.stdout.write(f"Répartition JCC : {distribution}")
        self.stdout.write(f"Cartes légendaires : {legendary_count}")
        catalogue_size = len(data["cards"]) + len(data.get("catalogue", []))
        self.stdout.write(f"Catalogue total (tirage du Qui est-ce ?) : {catalogue_size} espèces")

    @staticmethod
    def _tcg_type_for_card(card):
        """Résout le type explicite du fixture avec un repli déterministe."""

        tcg_type = card.get("tcg_type") or TCG_TYPE_BY_POKEDEX_ID.get(card["pokedex_id"])
        if tcg_type:
            tcg_type_definition = get_tcg_type(tcg_type)
            if tcg_type_definition is None:
                raise CommandError(f"Type JCC invalide pour le Pokémon #{card['pokedex_id']} : {tcg_type!r}.")
            return tcg_type_definition.slug

        # Les petits fixtures de test et les imports personnalisés restent
        # compatibles, tout en donnant la priorité à la sélection éditoriale.
        fallback = tcg_type_slug_for_source_type(card.get("primary_type"))
        if fallback is None:
            raise CommandError(f"Impossible de déterminer le type JCC du Pokémon #{card['pokedex_id']}.")
        return fallback

    def _fetch_from_api(self, catalogue_limit=0):
        """Récupère la pioche éditoriale, puis tout le reste du Pokédex.

        Les espèces hors pioche ne servent qu'au plateau du Qui est-ce ?, tiré
        au sort dans l'ensemble du catalogue : elles n'ont donc pas de type JCC
        éditorial et sont chargées avec ``in_current_deck=False``.
        """

        types = self._fetch_types()

        self.stdout.write(f"Récupération de {len(CURATED_POKEDEX_IDS)} Pokémon de la pioche...")
        cards = []
        for pokedex_id in CURATED_POKEDEX_IDS:
            card = self._fetch_card(pokedex_id)
            if card is None:
                raise CommandError(f"Le Pokémon #{pokedex_id} de la pioche est introuvable sur PokeAPI.")
            card["tcg_type"] = TCG_TYPE_BY_POKEDEX_ID[pokedex_id]
            cards.append(card)
            self.stdout.write(f"  #{pokedex_id} {card['name_fr']} / {card['name_en']}")

        catalogue_ids = [i for i in self._all_species_ids() if i not in set(CURATED_POKEDEX_IDS)]
        if catalogue_limit > 0:
            catalogue_ids = catalogue_ids[:catalogue_limit]

        self.stdout.write(f"Récupération de {len(catalogue_ids)} espèces supplémentaires...")
        catalogue = []
        skipped = []
        with ThreadPoolExecutor(max_workers=CATALOGUE_WORKERS) as pool:
            for pokedex_id, card in zip(catalogue_ids, pool.map(self._fetch_card, catalogue_ids)):
                if card is None:
                    skipped.append(pokedex_id)
                    continue
                catalogue.append(card)

        catalogue.sort(key=lambda card: card["pokedex_id"])
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(skipped)} espèces ignorées (illustration ou type indisponible) : "
                    f"{skipped[:10]}{'...' if len(skipped) > 10 else ''}"
                )
            )

        return {"types": types, "cards": cards, "catalogue": catalogue}

    def _fetch_types(self):
        """Nom français des 18 types source, seule base acceptée du catalogue."""

        import requests

        types = []
        for slug in ALL_TYPE_SLUGS:
            resp = requests.get(f"{POKEAPI_BASE}/type/{slug}", timeout=10)
            resp.raise_for_status()
            names = resp.json()["names"]
            types.append(
                {
                    "slug": slug,
                    "name_fr": next(n["name"] for n in names if n["language"]["name"] == "fr"),
                    "name_en": next(n["name"] for n in names if n["language"]["name"] == "en"),
                }
            )
        return types

    def _fetch_card(self, pokedex_id):
        """Une espèce du Pokédex, ou ``None`` si elle n'est pas exploitable."""

        import requests

        try:
            pokemon = requests.get(f"{POKEAPI_BASE}/pokemon/{pokedex_id}", timeout=20)
            pokemon.raise_for_status()
            pokemon = pokemon.json()
            species = requests.get(f"{POKEAPI_BASE}/pokemon-species/{pokedex_id}", timeout=20)
            species.raise_for_status()
            species = species.json()
        except requests.RequestException:
            return None

        type_slugs = [t["type"]["name"] for t in sorted(pokemon["types"], key=lambda t: t["slot"])]
        # Les types hors des 18 types source (« stellar », « unknown ») n'ont pas
        # de correspondance JCC : l'espèce est écartée plutôt que mal classée.
        if not type_slugs or any(slug not in ALL_TYPE_SLUGS for slug in type_slugs):
            return None

        sprite_url = pokemon["sprites"]["other"]["official-artwork"]["front_default"]
        if not sprite_url:
            return None

        names = species["names"]
        name_en = next((n["name"] for n in names if n["language"]["name"] == "en"), pokemon["name"])
        name_fr = next((n["name"] for n in names if n["language"]["name"] == "fr"), name_en)

        return {
            "pokedex_id": pokedex_id,
            "slug": pokemon["name"],
            "name_fr": name_fr,
            "name_en": name_en,
            "primary_type": type_slugs[0],
            "secondary_type": type_slugs[1] if len(type_slugs) > 1 else None,
            "sprite_url": sprite_url,
            "is_legendary": species["is_legendary"] or species["is_mythical"],
            "action": action_for_pokedex_id(pokedex_id),
        }

    @staticmethod
    def _all_species_ids():
        import requests

        resp = requests.get(f"{POKEAPI_BASE}/pokemon-species?limit=100000", timeout=30)
        resp.raise_for_status()
        return sorted(int(result["url"].rstrip("/").rsplit("/", 1)[-1]) for result in resp.json()["results"])
