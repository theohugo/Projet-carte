import itertools

from django.contrib.auth import get_user_model

from game.models import PokemonCard, PokemonType

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


def make_catalog(count=25):
    normal_type = PokemonType.objects.create(
        slug="normal",
        name_fr="Normal",
        name_en="Normal",
    )
    cards = []
    for index in range(1, count + 1):
        cards.append(
            PokemonCard.objects.create(
                pokedex_id=index,
                slug=f"pokemon-{index}",
                name_fr=f"Pokémon {index}",
                name_en=f"Pokemon {index}",
                primary_type=normal_type,
                tcg_type="colorless",
                sprite_url=f"https://example.com/{index}.png",
            )
        )
    return cards
