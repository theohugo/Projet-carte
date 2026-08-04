import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from game.models import PokemonCard, PokemonType
from game.pokemon_types import POKEMON_TYPE_SLUGS

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
            "--limit",
            type=int,
            default=0,
            help="Avec --from-api, limite le nombre d'espèces récupérées (0 = tout le Pokédex).",
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
            data = self._fetch_from_api(options["limit"])
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
        loaded_pokedex_ids = {card["pokedex_id"] for card in data["cards"]}
        # Une ancienne espèce peut encore être référencée par une partie. Elle
        # reste consultable dans l'historique, mais sort des nouveaux tirages.
        PokemonCard.objects.exclude(pokedex_id__in=loaded_pokedex_ids).update(in_current_deck=False)

        types_by_slug = {}
        for t in data["types"]:
            obj, _ = PokemonType.objects.update_or_create(
                slug=t["slug"],
                defaults={"name_fr": t["name_fr"], "name_en": t["name_en"]},
            )
            types_by_slug[t["slug"]] = obj

        for card in data["cards"]:
            PokemonCard.objects.update_or_create(
                pokedex_id=card["pokedex_id"],
                defaults={
                    "slug": card["slug"],
                    "name_fr": card["name_fr"],
                    "name_en": card["name_en"],
                    "primary_type": types_by_slug[card["primary_type"]],
                    "secondary_type": (
                        types_by_slug[card["secondary_type"]] if card.get("secondary_type") else None
                    ),
                    "sprite_url": card["sprite_url"],
                    "is_legendary": card["is_legendary"],
                    "in_current_deck": True,
                },
            )

        self.stdout.write(self.style.SUCCESS(f"{len(data['cards'])} espèces chargées au catalogue."))

    def _print_coverage_report(self, data):
        """Compte les espèces par type : chaque partie tire ses types parmi ceux
        qui en comptent assez, donc un type trop pauvre doit se voir."""

        type_counts = Counter()
        legendary_count = 0
        for card in data["cards"]:
            type_counts.update(slug for slug in (card["primary_type"], card.get("secondary_type")) if slug)
            if card["is_legendary"]:
                legendary_count += 1

        missing = set(POKEMON_TYPE_SLUGS) - set(type_counts)
        self.stdout.write(f"Types couverts : {len(type_counts)}/{len(POKEMON_TYPE_SLUGS)}")
        if missing:
            self.stdout.write(self.style.WARNING(f"Types manquants : {sorted(missing)}"))
        distribution = ", ".join(
            f"{slug}={type_counts.get(slug, 0)}"
            for slug in sorted(POKEMON_TYPE_SLUGS, key=lambda slug: -type_counts.get(slug, 0))
        )
        self.stdout.write(f"Espèces par type : {distribution}")
        self.stdout.write(f"Espèces légendaires : {legendary_count}")
        self.stdout.write(f"Catalogue total : {len(data['cards'])} espèces")

    def _fetch_from_api(self, limit=0):
        """Récupère tout le Pokédex : les parties tirent leurs types dedans."""

        types = self._fetch_types()

        species_ids = self._all_species_ids()
        if limit > 0:
            species_ids = species_ids[:limit]

        self.stdout.write(f"Récupération de {len(species_ids)} espèces depuis PokeAPI...")
        cards = []
        skipped = []
        with ThreadPoolExecutor(max_workers=CATALOGUE_WORKERS) as pool:
            for pokedex_id, card in zip(species_ids, pool.map(self._fetch_card, species_ids)):
                if card is None:
                    skipped.append(pokedex_id)
                    continue
                cards.append(card)

        cards.sort(key=lambda card: card["pokedex_id"])
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(skipped)} espèces ignorées (illustration ou type indisponible) : "
                    f"{skipped[:10]}{'...' if len(skipped) > 10 else ''}"
                )
            )

        return {"types": types, "cards": cards}

    def _fetch_types(self):
        """Nom français des 18 types source, seule base acceptée du catalogue."""

        import requests

        types = []
        for slug in POKEMON_TYPE_SLUGS:
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
        # Les types hors des 18 types source (« stellar », « unknown ») n'existent
        # pas dans le jeu : l'espèce est écartée plutôt que mal classée.
        if not type_slugs or any(slug not in POKEMON_TYPE_SLUGS for slug in type_slugs):
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
        }

    @staticmethod
    def _all_species_ids():
        import requests

        resp = requests.get(f"{POKEAPI_BASE}/pokemon-species?limit=100000", timeout=30)
        resp.raise_for_status()
        return sorted(int(result["url"].rstrip("/").rsplit("/", 1)[-1]) for result in resp.json()["results"])
