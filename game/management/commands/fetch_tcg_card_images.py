import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from game.pokemon_names import GEN_ONE_MAX_POKEDEX_ID
from game.seasons import SEASON_151, SEASON_BASE, SEASONS_BY_NUMBER, get_season

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"
TCGDEX_API_BASE = "https://api.tcgdex.net/v2/fr"
TCG_WORKERS = 4
TCG_MAX_ATTEMPTS = 5
TCG_RETRY_BACKOFF_SECONDS = 1.5
# Préférence pour les impressions du Set de Base originel : un visuel cohérent
# et reconnaissable d'une espèce à l'autre plutôt qu'une réimpression au hasard.
PREFERRED_SET_PREFIXES = ("base1-", "base2-", "base3-", "base4-", "base5-", "basep-")

# La série 151 tient dans un seul set : ses 151 premières cartes suivent le
# Pokédex, et les cartes ex ont en plus une illustration pleine page numérotée
# au-delà de 165. C'est celle-là qu'on garde, c'est la récompense du booster.
SET_151_ID = "sv03.5"
SET_151_FULL_ART_RANGE = range(182, 194)


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
            choices=sorted(SEASONS_BY_NUMBER),
            help="Saison à régénérer : 1 pour le Set de Base, 2 pour la série 151.",
        )
        parser.add_argument(
            "--fixture",
            type=Path,
            default=None,
            help="Chemin du fixture JSON à écrire. Par défaut, celui de la saison.",
        )

    def handle(self, *args, **options):
        season = get_season(options["saison"])
        fixture_path = options["fixture"] or FIXTURES_DIR / season.fixture

        self.stdout.write(
            f"Saison {season.number} — {season.label} : récupération depuis {TCGDEX_API_BASE}..."
        )
        if season.number == SEASON_151:
            images, missing = self._fetch_set_151()
        else:
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

    # ── Saison 2 : un seul appel, le set entier ───────────────────────────

    def _fetch_set_151(self):
        """Les 151 premières cartes du set, avec l'illustration pleine page des ex."""

        import requests

        try:
            resp = requests.get(f"{TCGDEX_API_BASE}/sets/{SET_151_ID}", timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Set {SET_151_ID} inaccessible : {exc}") from exc

        cards = resp.json().get("cards", [])
        # Les pleines pages portent le même nom que la carte ordinaire ; c'est
        # ce qui permet de les rattacher sans coder en dur douze numéros.
        full_arts = {
            card["name"]: card["image"]
            for card in cards
            if card.get("image") and self._local_id(card) in SET_151_FULL_ART_RANGE
        }

        images = {}
        for card in cards:
            local_id = self._local_id(card)
            if local_id is None or not (1 <= local_id <= GEN_ONE_MAX_POKEDEX_ID):
                continue
            image = full_arts.get(card["name"], card.get("image"))
            if image:
                images[str(local_id)] = f"{image}/high.png"

        missing = [i for i in range(1, GEN_ONE_MAX_POKEDEX_ID + 1) if str(i) not in images]
        return images, missing

    @staticmethod
    def _local_id(card):
        try:
            return int(card.get("localId"))
        except (TypeError, ValueError):
            return None
