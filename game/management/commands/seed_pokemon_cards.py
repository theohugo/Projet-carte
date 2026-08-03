import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from game.management.commands._pokedex_selection import ALL_TYPE_SLUGS, CURATED_POKEDEX_IDS
from game.models import PokemonCard, PokemonType

DEFAULT_FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "pokemon_cards.json"
POKEAPI_BASE = "https://pokeapi.co/api/v2"


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
            data = self._fetch_from_api()
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
        types_by_slug = {}
        for t in data["types"]:
            obj, _ = PokemonType.objects.update_or_create(
                slug=t["slug"],
                defaults={"name_fr": t["name_fr"], "name_en": t["name_en"]},
            )
            types_by_slug[t["slug"]] = obj

        for c in data["cards"]:
            PokemonCard.objects.update_or_create(
                pokedex_id=c["pokedex_id"],
                defaults={
                    "slug": c["slug"],
                    "name_fr": c["name_fr"],
                    "name_en": c["name_en"],
                    "primary_type": types_by_slug[c["primary_type"]],
                    "secondary_type": types_by_slug[c["secondary_type"]] if c.get("secondary_type") else None,
                    "sprite_url": c["sprite_url"],
                    "is_legendary": c["is_legendary"],
                },
            )

        self.stdout.write(self.style.SUCCESS(f"{len(data['cards'])} cartes chargées."))

    def _print_coverage_report(self, data):
        covered_types = set()
        legendary_count = 0
        for c in data["cards"]:
            covered_types.add(c["primary_type"])
            if c.get("secondary_type"):
                covered_types.add(c["secondary_type"])
            if c["is_legendary"]:
                legendary_count += 1

        missing = set(ALL_TYPE_SLUGS) - covered_types
        self.stdout.write(f"Types couverts : {len(covered_types)}/{len(ALL_TYPE_SLUGS)}")
        if missing:
            self.stdout.write(self.style.WARNING(f"Types manquants : {sorted(missing)}"))
        self.stdout.write(f"Cartes légendaires : {legendary_count}")

    def _fetch_from_api(self):
        import requests

        self.stdout.write(f"Récupération de {len(CURATED_POKEDEX_IDS)} Pokémon depuis PokeAPI...")

        type_cache = {}

        def get_type(slug):
            if slug not in type_cache:
                resp = requests.get(f"{POKEAPI_BASE}/type/{slug}", timeout=10)
                resp.raise_for_status()
                names = resp.json()["names"]
                name_fr = next(n["name"] for n in names if n["language"]["name"] == "fr")
                name_en = next(n["name"] for n in names if n["language"]["name"] == "en")
                type_cache[slug] = {"slug": slug, "name_fr": name_fr, "name_en": name_en}
            return type_cache[slug]

        cards = []
        for pokedex_id in CURATED_POKEDEX_IDS:
            pokemon = requests.get(f"{POKEAPI_BASE}/pokemon/{pokedex_id}", timeout=10).json()
            species = requests.get(f"{POKEAPI_BASE}/pokemon-species/{pokedex_id}", timeout=10).json()

            names = species["names"]
            name_fr = next(n["name"] for n in names if n["language"]["name"] == "fr")
            name_en = next(n["name"] for n in names if n["language"]["name"] == "en")

            type_slugs = [t["type"]["name"] for t in sorted(pokemon["types"], key=lambda t: t["slot"])]
            for slug in type_slugs:
                get_type(slug)

            sprite_url = pokemon["sprites"]["other"]["official-artwork"]["front_default"]

            cards.append(
                {
                    "pokedex_id": pokedex_id,
                    "slug": pokemon["name"],
                    "name_fr": name_fr,
                    "name_en": name_en,
                    "primary_type": type_slugs[0],
                    "secondary_type": type_slugs[1] if len(type_slugs) > 1 else None,
                    "sprite_url": sprite_url,
                    "is_legendary": species["is_legendary"] or species["is_mythical"],
                }
            )
            self.stdout.write(f"  #{pokedex_id} {name_fr} / {name_en} ({'+'.join(type_slugs)})")

        return {"types": list(type_cache.values()), "cards": cards}
