import itertools

from django.contrib.auth import get_user_model

from game.models import PokemonCard, PokemonType
from starterrace.services import STARTERS

_user_counter = itertools.count()


def make_users(count=5):
    User = get_user_model()
    return [
        User.objects.create_user(
            username=f"coureur-{next(_user_counter)}",
            email=f"secret-{index}@example.com",
            password="secret12345",
        )
        for index in range(count)
    ]


def make_starter_catalog():
    types = {
        "grass": PokemonType.objects.create(slug="grass", name_fr="Plante", name_en="Grass"),
        "fire": PokemonType.objects.create(slug="fire", name_fr="Feu", name_en="Fire"),
        "water": PokemonType.objects.create(slug="water", name_fr="Eau", name_en="Water"),
        "electric": PokemonType.objects.create(slug="electric", name_fr="Électrik", name_en="Electric"),
    }
    type_order = ("grass", "fire", "water", "electric")
    cards = []
    for descriptor, type_slug in zip(STARTERS, type_order, strict=True):
        pokedex_id = descriptor["pokedex_id"]
        cards.append(
            PokemonCard.objects.create(
                pokedex_id=pokedex_id,
                slug=f"starter-{pokedex_id}",
                name_fr=descriptor["name"],
                name_en=descriptor["name"],
                primary_type=types[type_slug],
                sprite_url=(
                    "https://raw.githubusercontent.com/PokeAPI/sprites/master/"
                    f"sprites/pokemon/other/official-artwork/{pokedex_id}.png"
                ),
            )
        )
    return cards


class FixedRng:
    def __init__(self, *values):
        self.values = iter(values)

    def randint(self, lower, upper):
        assert (lower, upper) == (1, 6)
        return next(self.values)
