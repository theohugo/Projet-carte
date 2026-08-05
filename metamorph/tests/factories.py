import itertools

from django.contrib.auth import get_user_model

from game.models import PokemonCard, PokemonType
from metamorph.services import DITTO_POKEDEX_ID, PAIR_COUNT

_user_counter = itertools.count()


def make_users(count=7):
    User = get_user_model()
    return [
        User.objects.create_user(
            username=f"collectionneur-{next(_user_counter)}",
            password="secret12345",
        )
        for _ in range(count)
    ]


def make_catalog(pair_count=PAIR_COUNT):
    normal_type, _ = PokemonType.objects.get_or_create(
        slug="normal",
        defaults={"name_fr": "Normal", "name_en": "Normal"},
    )
    cards = []
    for index in range(1, pair_count + 1):
        cards.append(
            PokemonCard.objects.create(
                pokedex_id=index,
                slug=f"mystere-{index}",
                name_fr=f"Pokémon secret {index}",
                name_en=f"Secret Pokemon {index}",
                primary_type=normal_type,
                sprite_url=f"https://assets.example.test/pokemon-{index}.png",
            )
        )
    ditto = PokemonCard.objects.create(
        pokedex_id=DITTO_POKEDEX_ID,
        slug="ditto",
        name_fr="Métamorph",
        name_en="Ditto",
        primary_type=normal_type,
        sprite_url="https://assets.example.test/ditto.png",
    )
    return cards, ditto
