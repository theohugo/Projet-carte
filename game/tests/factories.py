"""Petits ateliers de création d'objets de test (pas de fixture lourde)."""

import itertools

from django.contrib.auth import get_user_model

from game.models import Game, PokemonCard, PokemonType
from game.pokemon_types import SPECIES_PER_TYPE

User = get_user_model()

# Compteur global : garantit des usernames uniques même si make_users() est
# appelée plusieurs fois dans un même test (ex. pour ajouter un joueur de plus).
_user_counter = itertools.count()


def make_types():
    fire = PokemonType.objects.create(slug="fire", name_fr="Feu", name_en="Fire")
    water = PokemonType.objects.create(slug="water", name_fr="Eau", name_en="Water")
    grass = PokemonType.objects.create(slug="grass", name_fr="Plante", name_en="Grass")
    flying = PokemonType.objects.create(slug="flying", name_fr="Vol", name_en="Flying")
    poison = PokemonType.objects.create(slug="poison", name_fr="Poison", name_en="Poison")
    return {"fire": fire, "water": water, "grass": grass, "flying": flying, "poison": poison}


def make_draft_catalogue(types, per_type=SPECIES_PER_TYPE, start_pokedex_id=1000):
    """Catalogue minimal permettant un tirage de partie.

    `GameEngine.build_deck` exige au moins quatre types comptant chacun
    `SPECIES_PER_TYPE` espèces : les tests qui démarrent une vraie partie ont
    donc besoin d'un catalogue de cette taille, sans quoi le tirage échoue.
    """
    draftable = [types["fire"], types["water"], types["grass"], types["flying"]]
    species = []
    pokedex_id = start_pokedex_id
    for pokemon_type in draftable:
        for _ in range(per_type):
            species.append(
                PokemonCard(
                    pokedex_id=pokedex_id,
                    slug=f"espece-{pokedex_id}",
                    name_fr=f"Espèce {pokedex_id}",
                    name_en=f"Species {pokedex_id}",
                    primary_type=pokemon_type,
                    sprite_url=f"https://example.com/{pokedex_id}.png",
                )
            )
            pokedex_id += 1
    return PokemonCard.objects.bulk_create(species)


def make_cards(types):
    """4 cartes normales (une par type simple) + 1 légendaire double-type."""
    charmander = PokemonCard.objects.create(
        pokedex_id=4,
        slug="charmander",
        name_fr="Salamèche",
        name_en="Charmander",
        primary_type=types["fire"],
        sprite_url="https://example.com/4.png",
    )
    squirtle = PokemonCard.objects.create(
        pokedex_id=7,
        slug="squirtle",
        name_fr="Carapuce",
        name_en="Squirtle",
        primary_type=types["water"],
        sprite_url="https://example.com/7.png",
    )
    bulbasaur = PokemonCard.objects.create(
        pokedex_id=1,
        slug="bulbasaur",
        name_fr="Bulbizarre",
        name_en="Bulbasaur",
        primary_type=types["grass"],
        secondary_type=types["poison"],
        sprite_url="https://example.com/1.png",
    )
    charmander_evo = PokemonCard.objects.create(
        pokedex_id=5,
        slug="charmeleon",
        name_fr="Reptincel",
        name_en="Charmeleon",
        primary_type=types["fire"],
        sprite_url="https://example.com/5.png",
    )
    zapdos = PokemonCard.objects.create(
        pokedex_id=145,
        slug="zapdos",
        name_fr="Électhor",
        name_en="Zapdos",
        primary_type=types["flying"],
        sprite_url="https://example.com/145.png",
        is_legendary=True,
    )
    return {
        "charmander": charmander,
        "squirtle": squirtle,
        "bulbasaur": bulbasaur,
        "charmander_evo": charmander_evo,
        "zapdos": zapdos,
    }


def make_users(n=3):
    return [
        User.objects.create_user(username=f"joueur{next(_user_counter)}", password="pass12345")
        for _ in range(n)
    ]


def make_game(creator):
    return Game.objects.create(created_by=creator)
