import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from game.pokemon_names import GEN_ONE_MAX_POKEDEX_ID
from game.seasons import SEASON_151, SEASONS_BY_NUMBER, get_season, has_prints

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"
TCGDEX_API_BASE = "https://api.tcgdex.net/v2/fr"
TCG_WORKERS = 6
TCG_MAX_ATTEMPTS = 4
TCG_RETRY_BACKOFF_SECONDS = 1.5

SET_BY_SEASON = {SEASON_151: "sv03.5"}

# Les libellés de rareté de TCGdex, traduits en clés de `game.rarities`.
RARITY_KEYS = {
    "Commune": "COMMUNE",
    "Peu Commune": "PEU_COMMUNE",
    "Rare": "RARE",
    "Double rare": "DOUBLE_RARE",
    "Illustration rare": "ILLUSTRATION_RARE",
    "Ultra Rare": "ULTRA_RARE",
    "Illustration spéciale rare": "ILLUSTRATION_SPECIALE",
    "Hyper rare": "HYPER_RARE",
}


class Command(BaseCommand):
    help = (
        "Régénère le catalogue des impressions d'une saison depuis TCGdex : une "
        "entrée par carte du set, avec sa rareté réelle et son visuel. Ne touche "
        "pas au catalogue de jeu (PokemonCard), alimenté par PokeAPI."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--saison",
            type=int,
            default=SEASON_151,
            choices=sorted(SEASONS_BY_NUMBER),
            help="Saison à régénérer. Seules les saisons à impressions sont concernées.",
        )

    def handle(self, *args, **options):
        season = get_season(options["saison"])
        if not has_prints(season.number):
            raise CommandError(f"La saison {season.number} ne se décrit pas par ses impressions.")

        set_id = SET_BY_SEASON.get(season.number)
        if set_id is None:
            raise CommandError(f"Aucun set TCGdex connu pour la saison {season.number}.")

        self.stdout.write(f"Saison {season.number} — {season.label} : lecture du set {set_id}...")
        local_ids = self._set_local_ids(set_id)
        self.stdout.write(f"{len(local_ids)} cartes à détailler...")

        prints = []
        unknown = set()
        with ThreadPoolExecutor(max_workers=TCG_WORKERS) as pool:
            for card in pool.map(lambda lid: self._fetch_card(set_id, lid), local_ids):
                if card is None or card.get("category") != "Pokémon":
                    continue
                dex_ids = card.get("dexId") or []
                if not dex_ids or not (1 <= dex_ids[0] <= GEN_ONE_MAX_POKEDEX_ID):
                    continue
                key = RARITY_KEYS.get(card.get("rarity"))
                if key is None:
                    unknown.add(card.get("rarity"))
                    continue
                prints.append(
                    {
                        "local_id": int(card["localId"]),
                        "dex_id": dex_ids[0],
                        "name_fr": card["name"],
                        "rarity": key,
                        "image": f"{card['image']}/high.png",
                    }
                )

        prints.sort(key=lambda row: row["local_id"])
        path = FIXTURES_DIR / season.prints_fixture
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prints, ensure_ascii=False, indent=1), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"{len(prints)} impressions écrites -> {path}"))
        if unknown:
            self.stdout.write(self.style.WARNING(f"Raretés non traduites, ignorées : {sorted(unknown)}"))

    def _set_local_ids(self, set_id):
        import requests

        try:
            resp = requests.get(f"{TCGDEX_API_BASE}/sets/{set_id}", timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Set {set_id} inaccessible : {exc}") from exc

        local_ids = []
        for card in resp.json().get("cards", []):
            try:
                local_ids.append(int(card["localId"]))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(local_ids)

    @staticmethod
    def _fetch_card(set_id, local_id):
        """Le détail d'une carte — rareté et numéro de Pokédex compris."""

        import requests

        for attempt in range(TCG_MAX_ATTEMPTS):
            try:
                resp = requests.get(f"{TCGDEX_API_BASE}/cards/{set_id}-{local_id:03d}", timeout=25)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException:
                if attempt + 1 == TCG_MAX_ATTEMPTS:
                    return None
                time.sleep(TCG_RETRY_BACKOFF_SECONDS * (attempt + 1))
        return None
