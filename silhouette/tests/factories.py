import itertools

from django.contrib.auth import get_user_model

from game.models import PokemonCard, PokemonType

_user_counter = itertools.count()


def make_users(count=2):
    User = get_user_model()
    return [
        User.objects.create_user(username=f"devine-{next(_user_counter)}", password="secret12345")
        for _ in range(count)
    ]


def make_gen_one_catalog(count=12):
    """Quelques espèces de la première génération, seules éligibles au tirage."""

    electric, _ = PokemonType.objects.get_or_create(
        slug="electric", defaults={"name_fr": "Électrik", "name_en": "Electric"}
    )
    flying, _ = PokemonType.objects.get_or_create(
        slug="flying", defaults={"name_fr": "Vol", "name_en": "Flying"}
    )
    cards = []
    for index in range(1, count + 1):
        cards.append(
            PokemonCard.objects.create(
                pokedex_id=index,
                slug=f"gen-one-{index}",
                name_fr=f"Pokémon {index}",
                name_en=f"Pokemon {index}",
                primary_type=electric,
                secondary_type=flying if index % 2 == 0 else None,
                sprite_url=f"https://example.com/{index}.png",
            )
        )
    # Une espèce hors Gen 1 : elle ne doit jamais sortir.
    PokemonCard.objects.create(
        pokedex_id=800,
        slug="hors-gen-un",
        name_fr="Necrozma",
        name_en="Necrozma",
        primary_type=electric,
        sprite_url="https://example.com/800.png",
    )
    return cards
