from django.core.management.base import BaseCommand

from game.pokemon_types import POKEMON_TYPES
from game.type_icons import ICONS_DIR

# Les pastilles officielles rondes, telles que les jeux les affichent. Les noms
# de fichiers de la source sont en anglais majuscule ; nos slugs viennent de
# PokeAPI, d'où la table de correspondance.
SOURCE_BASE = "https://raw.githubusercontent.com/PokeMiners/pogo_assets/master/Images/Types"
SOURCE_NAMES = {
    "normal": "NORMAL",
    "fire": "FIRE",
    "water": "WATER",
    "electric": "ELECTRIC",
    "grass": "GRASS",
    "ice": "ICE",
    "fighting": "FIGHTING",
    "poison": "POISON",
    "ground": "GROUND",
    "flying": "FLYING",
    "psychic": "PSYCHIC",
    "bug": "BUG",
    "rock": "ROCK",
    "ghost": "GHOST",
    "dragon": "DRAGON",
    "dark": "DARK",
    "steel": "STEEL",
    "fairy": "FAIRY",
}


class Command(BaseCommand):
    help = (
        "Retélécharge les 18 pastilles officielles de type (PNG) dans les statiques. "
        "Les fichiers sont committés : cette commande ne sert qu'à les rafraîchir."
    )

    def handle(self, *args, **options):
        import requests

        ICONS_DIR.mkdir(parents=True, exist_ok=True)
        written = 0
        for pokemon_type in POKEMON_TYPES:
            source = SOURCE_NAMES.get(pokemon_type.slug)
            if source is None:
                self.stdout.write(self.style.WARNING(f"Pas de source pour {pokemon_type.slug}"))
                continue

            try:
                resp = requests.get(f"{SOURCE_BASE}/POKEMON_TYPE_{source}.png", timeout=20)
                resp.raise_for_status()
            except requests.RequestException as exc:
                self.stdout.write(self.style.WARNING(f"{pokemon_type.slug} : {exc}"))
                continue

            (ICONS_DIR / f"{pokemon_type.slug}.png").write_bytes(resp.content)
            written += 1

        self.stdout.write(self.style.SUCCESS(f"{written} pictogrammes écrits -> {ICONS_DIR}"))
