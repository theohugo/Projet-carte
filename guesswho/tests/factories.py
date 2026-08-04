import itertools

from django.contrib.auth import get_user_model

from game.models import PokemonCard, PokemonType
from guesswho.services import ROSTER_SIZE

_user_counter = itertools.count()


def make_users(count=3):
    User = get_user_model()
    return [
        User.objects.create_user(
            username=f"devineur-{next(_user_counter)}",
            password="secret12345",
        )
        for _ in range(count)
    ]


def make_catalog(count=ROSTER_SIZE, start=1):
    """Catalogue de test. `count` par défaut = ROSTER_SIZE : le tirage
    aléatoire du plateau inclut alors systématiquement toutes les cartes,
    pour des tests déterministes. Passer un `count` plus grand (et un
    `start` distinct pour éviter les collisions de pokedex_id) pour les
    tests qui exercent spécifiquement l'exclusion aléatoire."""
    normal_type, _ = PokemonType.objects.get_or_create(
        slug="normal",
        defaults={"name_fr": "Normal", "name_en": "Normal"},
    )
    cards = []
    for index in range(start, start + count):
        cards.append(
            PokemonCard.objects.create(
                pokedex_id=index,
                slug=f"pokemon-{index}",
                name_fr=f"Pokémon {index}",
                name_en=f"Pokemon {index}",
                primary_type=normal_type,
                sprite_url=f"https://example.com/{index}.png",
            )
        )
    return cards
