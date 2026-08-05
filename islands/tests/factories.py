import itertools

from django.contrib.auth import get_user_model

from game.models import PokemonCard, PokemonType
from islands.services import place_formation, ready_player

_user_counter = itertools.count()


def make_users(count=3):
    User = get_user_model()
    return [
        User.objects.create_user(
            username=f"marin-{next(_user_counter)}",
            password="secret12345",
        )
        for _ in range(count)
    ]


def make_catalog(water_count=8, other_count=0, start=1):
    water, _ = PokemonType.objects.get_or_create(
        slug="water",
        defaults={"name_fr": "Eau", "name_en": "Water"},
    )
    normal, _ = PokemonType.objects.get_or_create(
        slug="normal",
        defaults={"name_fr": "Normal", "name_en": "Normal"},
    )
    cards = []
    for offset in range(water_count + other_count):
        index = start + offset
        is_water = offset < water_count
        cards.append(
            PokemonCard.objects.create(
                pokedex_id=5000 + index,
                slug=f"island-pokemon-{index}",
                name_fr=f"Pokémon marin {index}",
                name_en=f"Sea Pokemon {index}",
                primary_type=water if is_water else normal,
                sprite_url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{index}.png",
            )
        )
    return cards


def deploy_all(game, user):
    """Placement déterministe sans chevauchement pour une suite de tests."""

    player = game.players.get(user=user)
    placements = {
        0: (0, 0, "H"),
        1: (1, 0, "H"),
        2: (2, 0, "V"),
        3: (7, 0, "H"),
    }
    for formation in player.formations.order_by("slot"):
        row, col, orientation = placements[formation.slot]
        game = place_formation(
            game.id,
            user,
            formation.id,
            row,
            col,
            orientation,
            game.turn_revision,
        )
    return game


def ready_both(game, host, guest):
    game = deploy_all(game, host)
    game = deploy_all(game, guest)
    game = ready_player(game.id, host, game.turn_revision)
    return ready_player(game.id, guest, game.turn_revision)
