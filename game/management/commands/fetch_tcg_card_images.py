import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from game.pokemon_names import GEN_ONE_MAX_POKEDEX_ID
from game.seasons import SEASON_BASE, get_season, has_prints

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"
TCGDEX_API_BASE = "https://api.tcgdex.net/v2/fr"
TCG_WORKERS = 4
TCG_MAX_ATTEMPTS = 5
TCG_RETRY_BACKOFF_SECONDS = 1.5
# Préférence pour les impressions du Set de Base originel : un visuel cohérent
# et reconnaissable d'une espèce à l'autre plutôt qu'une réimpression au hasard.
PREFERRED_SET_PREFIXES = ("base1-", "base2-", "base3-", "base4-", "base5-", "basep-")


class Command(BaseCommand):
    help = (
        "Régénère un fixture de visuels de vraies cartes TCG françaises (TCGdex), "
        "utilisé uniquement pour l'illustration des cartes de la page Collection. "
        "Ne touche pas au catalogue de jeu (PokemonCard), alimenté par PokeAPI."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--saison",
            type=int,
            default=SEASON_BASE,
            help="Saison à régénérer. Une saison à impressions passe par fetch_card_prints.",
        )
        parser.add_argument(
            "--fixture",
            type=Path,
            default=None,
            help="Chemin du fixture JSON à écrire. Par défaut, celui de la saison.",
        )

    def handle(self, *args, **options):
        season = get_season(options["saison"])
        if has_prints(season.number):
            raise CommandError(
                f"La saison {season.number} se décrit par ses impressions : "
                "utilise plutôt `manage.py fetch_card_prints`."
            )
        fixture_path = options["fixture"] or FIXTURES_DIR / season.fixture

        self.stdout.write(
            f"Saison {season.number} — {season.label} : récupération depuis {TCGDEX_API_BASE}..."
        )
        images, missing = self._fetch_base_set()

        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(
            json.dumps(images, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        self.stdout.write(self.style.SUCCESS(f"{len(images)} visuels récupérés -> {fixture_path}"))
        if missing:
            self.stdout.write(self.style.WARNING(f"Aucune carte trouvée pour : {missing}"))

    # ── Saison 1 : une requête par numéro de Pokédex ──────────────────────

    def _fetch_base_set(self):
        pokedex_ids = range(1, GEN_ONE_MAX_POKEDEX_ID + 1)
        images = {}
        missing = []
        with ThreadPoolExecutor(max_workers=TCG_WORKERS) as pool:
            for pokedex_id, image_url in zip(pokedex_ids, pool.map(self._fetch_image, pokedex_ids)):
                if image_url:
                    images[str(pokedex_id)] = image_url
                else:
                    missing.append(pokedex_id)
        return images, missing

    @classmethod
    def _fetch_image(cls, pokedex_id):
        """Le visuel d'impression française la plus proche du Set de Base, ou ``None``.

        Les échecs réseau/HTTP sont retentés : seule une réponse exploitable
        sans résultat vaut absence réelle de carte.
        """

        import requests

        for attempt in range(TCG_MAX_ATTEMPTS):
            try:
                resp = requests.get(
                    f"{TCGDEX_API_BASE}/cards",
                    params={"dexId": f"eq:{pokedex_id}"},
                    timeout=20,
                )
                resp.raise_for_status()
            except requests.RequestException:
                if attempt + 1 == TCG_MAX_ATTEMPTS:
                    return None
                time.sleep(TCG_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

            results = [card for card in resp.json() if card.get("image")]
            if not results:
                return None

            card = next(
                (c for c in results if c["id"].startswith(PREFERRED_SET_PREFIXES)),
                results[0],
            )
            return f"{card['image']}/high.png"

        return None
