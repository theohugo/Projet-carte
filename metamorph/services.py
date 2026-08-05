import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from game.models import PokemonCard
from game.results import record_completed_game

from .models import MetamorphCard, MetamorphGame, MetamorphMove, MetamorphPlayer

MIN_PLAYERS = 2
MAX_PLAYERS = 6
PAIR_COUNT = 12
DITTO_POKEDEX_ID = 132


class MetamorphError(Exception):
    """Erreur métier pouvant être affichée sans exposer l'état interne."""


class MetamorphPermissionError(MetamorphError):
    pass


class MetamorphStateError(MetamorphError):
    pass


class MetamorphCatalogError(MetamorphError):
    pass


@dataclass(frozen=True, slots=True)
class StaleRevisionError(MetamorphError):
    expected: int
    actual: int

    def __str__(self):
        return "La partie a changé entre-temps. Son état a été actualisé."


def _lock_game(game_id) -> MetamorphGame:
    return MetamorphGame.objects.select_for_update().get(pk=game_id)


def _players_locked(game: MetamorphGame) -> list[MetamorphPlayer]:
    return list(game.players.select_for_update().select_related("user").order_by("turn_order"))


def _player_for_user(players: list[MetamorphPlayer], user) -> MetamorphPlayer:
    player = next((entry for entry in players if entry.user_id == user.id), None)
    if player is None:
        raise MetamorphPermissionError("Vous ne participez pas à cette partie.")
    return player


def _assert_revision(game: MetamorphGame, expected_revision: int):
    if expected_revision != game.turn_revision:
        raise StaleRevisionError(expected=expected_revision, actual=game.turn_revision)


def _bump_revision(game: MetamorphGame, *update_fields: str):
    game.turn_revision += 1
    game.save(update_fields=[*update_fields, "turn_revision"])


def _ditto_card() -> PokemonCard | None:
    return (
        PokemonCard.objects.filter(
            Q(pokedex_id=DITTO_POKEDEX_ID)
            | Q(slug__iexact="ditto")
            | Q(name_fr__iexact="Métamorph")
            | Q(name_en__iexact="Ditto")
        )
        .order_by("pokedex_id")
        .first()
    )


def _catalog_deck() -> tuple[PokemonCard, list[PokemonCard]]:
    ditto = _ditto_card()
    if ditto is None:
        raise MetamorphCatalogError("Le catalogue doit contenir Métamorph (#132) pour lancer une partie.")
    pool = list(PokemonCard.objects.exclude(pk=ditto.pk))
    if len(pool) < PAIR_COUNT:
        raise MetamorphCatalogError(f"Le mode nécessite Métamorph et au moins {PAIR_COUNT} autres Pokémon.")
    return ditto, random.sample(pool, PAIR_COUNT)


@transaction.atomic
def create_game(user) -> MetamorphGame:
    game = MetamorphGame.objects.create(created_by=user)
    MetamorphPlayer.objects.create(game=game, user=user, turn_order=0)
    return game


@transaction.atomic
def join_game(game_id, user) -> tuple[MetamorphGame, MetamorphPlayer]:
    game = _lock_game(game_id)
    players = _players_locked(game)
    existing = next((entry for entry in players if entry.user_id == user.id), None)
    if existing is not None:
        return game, existing
    if game.status != MetamorphGame.Status.EN_ATTENTE:
        raise MetamorphStateError("Cette partie a déjà commencé.")
    if len(players) >= MAX_PLAYERS:
        raise MetamorphStateError("Cette table est complète.")

    player = MetamorphPlayer.objects.create(
        game=game,
        user=user,
        turn_order=len(players),
    )
    _bump_revision(game)
    return game, player


def _rank_empty_player(game: MetamorphGame, player: MetamorphPlayer, moment) -> bool:
    if player.rank is not None or game.cards.filter(owner=player).exists():
        return False
    latest_rank = game.players.aggregate(latest=Max("rank"))["latest"] or 0
    player.rank = latest_rank + 1
    player.finished_at = moment
    player.save(update_fields=["rank", "finished_at"])
    return True


def _finish_if_one_holder(
    game: MetamorphGame,
    players: list[MetamorphPlayer],
    moment,
) -> MetamorphPlayer | None:
    owner_ids = set(game.cards.filter(owner__isnull=False).values_list("owner_id", flat=True).distinct())
    if len(owner_ids) > 1:
        return None
    if not owner_ids:
        raise MetamorphStateError("La carte Métamorph est introuvable dans les mains.")

    loser = next(entry for entry in players if entry.id in owner_ids)
    remaining = list(game.cards.filter(owner=loser))
    if len(remaining) != 1 or not remaining[0].is_ditto:
        raise MetamorphStateError("La fin de partie ne peut pas encore être déterminée.")

    for player in players:
        if player.id != loser.id:
            _rank_empty_player(game, player, moment)

    loser.rank = len(players)
    loser.is_loser = True
    loser.finished_at = moment
    loser.save(update_fields=["rank", "is_loser", "finished_at"])
    game.status = MetamorphGame.Status.TERMINEE
    game.current_turn = None
    game.finished_at = moment
    return loser


def _record_finished_game(players: list[MetamorphPlayer], loser: MetamorphPlayer):
    record_completed_game(
        (player.user for player in players),
        (player.user_id for player in players if player.id != loser.id),
    )


@transaction.atomic
def start_game(game_id, user, expected_revision: int) -> MetamorphGame:
    game = _lock_game(game_id)
    players = _players_locked(game)
    _player_for_user(players, user)
    _assert_revision(game, expected_revision)
    if game.created_by_id != user.id:
        raise MetamorphPermissionError("Seul l'hôte peut lancer la partie.")
    if game.status != MetamorphGame.Status.EN_ATTENTE:
        raise MetamorphStateError("Cette partie a déjà commencé.")
    if not MIN_PLAYERS <= len(players) <= MAX_PLAYERS:
        raise MetamorphStateError("Il faut entre 2 et 6 joueurs pour commencer.")

    ditto, pair_species = _catalog_deck()
    deck = [(pokemon, copy_index, False) for pokemon in pair_species for copy_index in (0, 1)]
    deck.append((ditto, 0, True))
    random.shuffle(deck)

    dealt: dict[int, list[tuple[PokemonCard, int, bool]]] = {player.id: [] for player in players}
    for index, physical_card in enumerate(deck):
        dealt[players[index % len(players)].id].append(physical_card)

    moment = timezone.now()
    card_rows = []
    for player in players:
        hand = dealt[player.id]
        species_counts: dict[int, int] = {}
        for pokemon, _copy_index, is_ditto in hand:
            if not is_ditto:
                species_counts[pokemon.id] = species_counts.get(pokemon.id, 0) + 1
        paired_species = {pokemon_id for pokemon_id, count in species_counts.items() if count >= 2}
        hand_position = 0
        for pokemon, copy_index, is_ditto in hand:
            is_initial_pair = not is_ditto and pokemon.id in paired_species
            if not is_initial_pair:
                hand_position += 1
            card_rows.append(
                MetamorphCard(
                    game=game,
                    pokemon_card=pokemon,
                    owner=None if is_initial_pair else player,
                    copy_index=copy_index,
                    is_ditto=is_ditto,
                    hand_position=0 if is_initial_pair else hand_position,
                    paired_at=moment if is_initial_pair else None,
                )
            )
    MetamorphCard.objects.bulk_create(card_rows)

    for player in players:
        _rank_empty_player(game, player, moment)

    game.status = MetamorphGame.Status.EN_COURS
    game.started_at = moment
    loser = _finish_if_one_holder(game, players, moment)
    if loser is None:
        game.current_turn = next(player for player in players if player.rank is None)
        _bump_revision(game, "status", "started_at", "current_turn")
    else:
        _bump_revision(game, "status", "started_at", "current_turn", "finished_at")
        _record_finished_game(players, loser)
    return game


def _relative_player_with_cards(
    players: list[MetamorphPlayer],
    current: MetamorphPlayer,
    direction: int,
    owner_ids: set[int],
    *,
    source: bool,
) -> MetamorphPlayer | None:
    current_index = next(index for index, entry in enumerate(players) if entry.id == current.id)
    step = -direction if source else direction
    for distance in range(1, len(players) + 1):
        candidate = players[(current_index + step * distance) % len(players)]
        if candidate.id != current.id and candidate.id in owner_ids and candidate.rank is None:
            return candidate
    return None


def _compact_hand(cards: list[MetamorphCard]):
    changed = []
    for position, card in enumerate(
        sorted(cards, key=lambda entry: (entry.hand_position, entry.id)),
        start=1,
    ):
        if card.hand_position != position:
            card.hand_position = position
            changed.append(card)
    if changed:
        MetamorphCard.objects.bulk_update(changed, ["hand_position"])


@transaction.atomic
def draw_card(
    game_id,
    user,
    card_position: int,
    expected_revision: int,
) -> MetamorphGame:
    game = _lock_game(game_id)
    players = _players_locked(game)
    actor = _player_for_user(players, user)
    _assert_revision(game, expected_revision)
    if game.status != MetamorphGame.Status.EN_COURS:
        raise MetamorphStateError("La partie n'est pas en cours.")
    if game.current_turn_id != actor.id:
        raise MetamorphStateError("Ce n'est pas votre tour.")
    if isinstance(card_position, bool) or not isinstance(card_position, int) or card_position <= 0:
        raise MetamorphStateError("Choisissez une carte face cachée valide.")

    locked_cards = list(
        game.cards.select_for_update()
        .select_related("pokemon_card__primary_type", "pokemon_card__secondary_type")
        .filter(owner__isnull=False)
        .order_by("owner_id", "hand_position", "id")
    )
    owner_ids = {card.owner_id for card in locked_cards}
    source = _relative_player_with_cards(
        players,
        actor,
        game.direction,
        owner_ids,
        source=True,
    )
    if source is None:
        raise MetamorphStateError("Aucune main adverse ne peut être piochée.")

    source_hand = [card for card in locked_cards if card.owner_id == source.id]
    drawn = next(
        (card for card in source_hand if card.hand_position == card_position),
        None,
    )
    if drawn is None:
        raise MetamorphStateError("Cette carte n'est plus disponible.")

    actor_hand = [card for card in locked_cards if card.owner_id == actor.id]
    drawn.owner = actor
    drawn.hand_position = len(actor_hand) + 1
    drawn.save(update_fields=["owner", "hand_position"])
    source_hand.remove(drawn)
    _compact_hand(source_hand)

    matching_card = None
    if not drawn.is_ditto:
        matching_card = next(
            (
                card
                for card in actor_hand
                if not card.is_ditto and card.pokemon_card_id == drawn.pokemon_card_id
            ),
            None,
        )
    if matching_card is not None:
        moment = timezone.now()
        for card in (drawn, matching_card):
            card.owner = None
            card.hand_position = 0
            card.paired_at = moment
        MetamorphCard.objects.bulk_update(
            [drawn, matching_card],
            ["owner", "hand_position", "paired_at"],
        )
    else:
        moment = timezone.now()

    sequence = (game.moves.aggregate(latest=Max("sequence"))["latest"] or 0) + 1
    MetamorphMove.objects.create(
        game=game,
        sequence=sequence,
        actor=actor,
        source=source,
        drawn_card=drawn,
        paired_card=matching_card,
        formed_pair=matching_card is not None,
        resulting_revision=game.turn_revision + 1,
    )

    _rank_empty_player(game, source, moment)
    _rank_empty_player(game, actor, moment)
    loser = _finish_if_one_holder(game, players, moment)
    if loser is None:
        remaining_owner_ids = set(
            game.cards.filter(owner__isnull=False).values_list("owner_id", flat=True).distinct()
        )
        next_player = _relative_player_with_cards(
            players,
            actor,
            game.direction,
            remaining_owner_ids,
            source=False,
        )
        if next_player is None:
            raise MetamorphStateError("Le prochain joueur n'a pas pu être déterminé.")
        game.current_turn = next_player
        _bump_revision(game, "current_turn")
    else:
        _bump_revision(game, "status", "current_turn", "finished_at")
        _record_finished_game(players, loser)
    return game


def _serialize_pokemon(card: PokemonCard) -> dict:
    return {
        "id": card.id,
        "pokedex_id": card.pokedex_id,
        "slug": card.slug,
        "name_fr": card.name_fr,
        "name_en": card.name_en,
        "sprite_url": card.sprite_url,
        "primary_type": {
            "slug": card.primary_type.slug,
            "name_fr": card.primary_type.name_fr,
        },
        "secondary_type": (
            {
                "slug": card.secondary_type.slug,
                "name_fr": card.secondary_type.name_fr,
            }
            if card.secondary_type
            else None
        ),
    }


def _serialize_player(player: MetamorphPlayer, hand_count: int, me_id: int) -> dict:
    return {
        "id": player.id,
        "username": player.user.get_username(),
        "turn_order": player.turn_order,
        "hand_count": hand_count,
        "rank": player.rank,
        "is_loser": player.is_loser,
        "is_me": player.id == me_id,
    }


def _source_for_state(
    game: MetamorphGame,
    players: list[MetamorphPlayer],
    hand_counts: dict[int, int],
) -> MetamorphPlayer | None:
    current = next((entry for entry in players if entry.id == game.current_turn_id), None)
    if current is None:
        return None
    return _relative_player_with_cards(
        players,
        current,
        game.direction,
        {player_id for player_id, count in hand_counts.items() if count > 0},
        source=True,
    )


def serialize_game_state(game: MetamorphGame, user) -> dict:
    """Retourne un état personnalisé sans le contenu d'aucune main adverse."""

    players = list(game.players.select_related("user").order_by("turn_order"))
    me = next((entry for entry in players if entry.user_id == user.id), None)
    if me is None:
        raise MetamorphPermissionError("Vous ne participez pas à cette partie.")

    hand_counts = {
        row["owner_id"]: row["count"]
        for row in game.cards.filter(owner__isnull=False).values("owner_id").annotate(count=Count("id"))
    }
    serialized_players = [
        _serialize_player(player, hand_counts.get(player.id, 0), me.id) for player in players
    ]
    player_payload_by_id = {entry["id"]: entry for entry in serialized_players}

    own_cards = list(
        game.cards.filter(owner=me)
        .select_related("pokemon_card__primary_type", "pokemon_card__secondary_type")
        .order_by("hand_position", "id")
    )
    paired_cards = list(
        game.cards.filter(paired_at__isnull=False)
        .select_related("pokemon_card__primary_type", "pokemon_card__secondary_type")
        .order_by("paired_at", "pokemon_card__pokedex_id", "copy_index")
    )
    paired_species = []
    seen_pokemon_ids = set()
    for card in paired_cards:
        if card.pokemon_card_id in seen_pokemon_ids:
            continue
        seen_pokemon_ids.add(card.pokemon_card_id)
        paired_species.append(_serialize_pokemon(card.pokemon_card))

    moves = []
    for move in game.moves.select_related(
        "actor__user",
        "source__user",
        "drawn_card__pokemon_card__primary_type",
        "drawn_card__pokemon_card__secondary_type",
    ):
        moves.append(
            {
                "id": move.id,
                "sequence": move.sequence,
                "actor": {
                    "id": move.actor_id,
                    "username": move.actor.user.get_username(),
                },
                "source": {
                    "id": move.source_id,
                    "username": move.source.user.get_username(),
                },
                "formed_pair": move.formed_pair,
                # Une carte non appariée rejoint une main et reste donc secrète.
                "pair": (_serialize_pokemon(move.drawn_card.pokemon_card) if move.formed_pair else None),
                "created_at": move.created_at.isoformat(),
            }
        )

    can_draw = (
        game.status == MetamorphGame.Status.EN_COURS and game.current_turn_id == me.id and me.rank is None
    )
    source = _source_for_state(game, players, hand_counts)
    draw_source = None
    if source is not None:
        source_count = hand_counts.get(source.id, 0)
        draw_source = {
            "player": {
                "id": source.id,
                "username": source.user.get_username(),
            },
            "card_count": source_count,
            # Les positions suffisent à choisir. Aucun identifiant de carte ou
            # de Pokémon adverse ne traverse la frontière JSON.
            "hidden_cards": (
                [{"position": position} for position in range(1, source_count + 1)] if can_draw else []
            ),
        }

    standings = sorted(
        (entry for entry in serialized_players if entry["rank"] is not None),
        key=lambda entry: entry["rank"],
    )
    current_turn = player_payload_by_id.get(game.current_turn_id)
    loser = next((entry for entry in serialized_players if entry["is_loser"]), None)
    return {
        "game_id": str(game.id),
        "status": game.status,
        "turn_revision": game.turn_revision,
        "direction": game.direction,
        "min_players": MIN_PLAYERS,
        "max_players": MAX_PLAYERS,
        "is_host": game.created_by_id == user.id,
        "can_start": (
            game.status == MetamorphGame.Status.EN_ATTENTE
            and game.created_by_id == user.id
            and len(players) >= MIN_PLAYERS
        ),
        "can_draw": can_draw,
        "current_turn": current_turn,
        "players": serialized_players,
        "me": {
            **player_payload_by_id[me.id],
            "hand": [
                {
                    "physical_id": card.id,
                    "position": card.hand_position,
                    "is_ditto": card.is_ditto,
                    "pokemon": _serialize_pokemon(card.pokemon_card),
                }
                for card in own_cards
            ],
        },
        "draw_source": draw_source,
        "paired_pokemon": paired_species,
        "moves": moves,
        "standings": standings,
        "loser": loser,
    }


def get_lobby_state(user) -> dict:
    open_games = list(
        MetamorphGame.objects.filter(status=MetamorphGame.Status.EN_ATTENTE)
        .select_related("created_by")
        .annotate(player_count=Count("players"))
        .filter(player_count__lt=MAX_PLAYERS)
        .order_by("-created_at")
    )
    my_games = list(
        MetamorphGame.objects.annotate(player_count=Count("players", distinct=True))
        .filter(players__user=user)
        .select_related("created_by")
        .distinct()
        .order_by("-created_at")
    )
    return {
        "open_games": [
            {
                "id": str(game.id),
                "creator": game.created_by.get_username(),
                "player_count": game.player_count,
                "max_players": MAX_PLAYERS,
                "status": game.status,
            }
            for game in open_games
        ],
        "my_games": [
            {
                "id": str(game.id),
                "status": game.status,
                "player_count": game.player_count,
            }
            for game in my_games
        ],
        "my_game_ids": [str(game.id) for game in my_games],
    }
