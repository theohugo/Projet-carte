"""Moteur transactionnel d'Infiltration Rocket.

La règle essentielle de ce module est la séparation des informations : toutes
les mutations et toute la sérialisation passent ici afin qu'un client ne puisse
jamais déduire les rôles adverses depuis une réponse HTML ou JSON.
"""

import random
from collections import Counter
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.templatetags.static import static
from django.utils import timezone

from game.results import record_completed_game

from .models import RocketGame, RocketMessage, RocketNightAction, RocketPlayer, RocketVote

MIN_PLAYERS = 6
MAX_PLAYERS = 12
MAX_MESSAGE_LENGTH = 300
NIGHT_SECONDS = 120
DISCUSSION_SECONDS = 180
VOTE_SECONDS = 90

ROLE_PRESENTATION = {
    RocketPlayer.Role.ROCKET: {
        "name": "Agent Rocket",
        "side": "Team Rocket",
        "mission": "Sabote un Dresseur chaque nuit et reste indétectable pendant les votes.",
        "artwork": "img/games/artwork/meowth.png",
    },
    RocketPlayer.Role.DETECTIVE: {
        "name": "Détective Looker",
        "side": "Alliance des Dresseurs",
        "mission": "Enquête chaque nuit sur un joueur pour savoir s'il appartient à la Team Rocket.",
        "artwork": "img/games/artwork/lucario.png",
    },
    RocketPlayer.Role.GUARDIAN: {
        "name": "Leuphorie gardienne",
        "side": "Alliance des Dresseurs",
        "mission": "Protège un joueur chaque nuit contre le sabotage de la Team Rocket.",
        "artwork": "img/games/artwork/chansey.png",
    },
    RocketPlayer.Role.TRAINER: {
        "name": "Dresseur",
        "side": "Alliance des Dresseurs",
        "mission": "Observe les débats, repère les incohérences et vote pour démasquer les agents.",
        "artwork": "img/games/artwork/pikachu.png",
    },
}


class RocketError(Exception):
    """Erreur de règle sûre à présenter au joueur."""


class RocketPermissionError(RocketError):
    pass


class StaleRevisionError(RocketError):
    pass


def rocket_count_for(player_count: int) -> int:
    if player_count < 8:
        return 1
    if player_count < 11:
        return 2
    return 3


def _bump(game: RocketGame, *fields: str) -> None:
    game.turn_revision += 1
    game.save(update_fields=[*fields, "turn_revision"])


def _player_for(game: RocketGame, user) -> RocketPlayer:
    player = game.players.select_related("user").filter(user=user).first()
    if player is None:
        raise RocketPermissionError("Vous ne participez pas à cette infiltration.")
    return player


def _assert_revision(game: RocketGame, expected_revision) -> None:
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise RocketError("La révision de partie est obligatoire.")
    if expected_revision != game.turn_revision:
        raise StaleRevisionError("La partie a changé entre-temps. Elle a été actualisée.")


@transaction.atomic
def create_game(user) -> RocketGame:
    game = RocketGame.objects.create(created_by=user, max_players=MAX_PLAYERS)
    RocketPlayer.objects.create(game=game, user=user, turn_order=0)
    return game


@transaction.atomic
def join_game(game_id, user) -> RocketGame:
    game = RocketGame.objects.select_for_update().get(pk=game_id)
    if game.status != RocketGame.Status.EN_ATTENTE:
        raise RocketError("Cette infiltration a déjà commencé.")
    if game.players.filter(user=user).exists():
        return game
    if game.players.count() >= game.max_players:
        raise RocketError("Cette infiltration est complète.")
    next_order = (game.players.aggregate(top=Max("turn_order"))["top"] or 0) + 1
    RocketPlayer.objects.create(game=game, user=user, turn_order=next_order)
    _bump(game)
    return game


@transaction.atomic
def start_game(game_id, user) -> RocketGame:
    game = RocketGame.objects.select_for_update().get(pk=game_id)
    if game.created_by_id != user.id:
        raise RocketPermissionError("Seul l'hôte peut distribuer les rôles.")
    if game.status != RocketGame.Status.EN_ATTENTE:
        raise RocketError("Cette infiltration a déjà commencé.")

    players = list(game.players.select_related("user").order_by("turn_order"))
    if len(players) < MIN_PLAYERS:
        raise RocketError(f"Il faut au moins {MIN_PLAYERS} joueurs pour cacher les rôles.")
    if len(players) > MAX_PLAYERS:
        raise RocketError(f"Une infiltration accepte au maximum {MAX_PLAYERS} joueurs.")

    roles = [RocketPlayer.Role.ROCKET] * rocket_count_for(len(players))
    roles += [RocketPlayer.Role.DETECTIVE, RocketPlayer.Role.GUARDIAN]
    roles += [RocketPlayer.Role.TRAINER] * (len(players) - len(roles))
    random.shuffle(roles)
    for player, role in zip(players, roles, strict=True):
        player.role = role
        player.is_alive = True
    RocketPlayer.objects.bulk_update(players, ["role", "is_alive"])

    game.status = RocketGame.Status.NUIT
    game.round_number = 1
    game.started_at = timezone.now()
    game.last_event = {}
    game.phase_deadline = timezone.now() + timedelta(seconds=NIGHT_SECONDS)
    _bump(game, "status", "round_number", "started_at", "last_event", "phase_deadline")
    return game


def _action_kind(role: str) -> str | None:
    return {
        RocketPlayer.Role.ROCKET: RocketNightAction.Kind.KILL,
        RocketPlayer.Role.DETECTIVE: RocketNightAction.Kind.INSPECT,
        RocketPlayer.Role.GUARDIAN: RocketNightAction.Kind.PROTECT,
    }.get(role)


def _check_target(actor: RocketPlayer, target: RocketPlayer, kind: str) -> None:
    if target.game_id != actor.game_id or not target.is_alive:
        raise RocketError("Cette cible n'est pas disponible.")
    if kind in {RocketNightAction.Kind.KILL, RocketNightAction.Kind.INSPECT} and target.pk == actor.pk:
        raise RocketError("Choisis un autre joueur.")
    if kind == RocketNightAction.Kind.KILL and target.role == RocketPlayer.Role.ROCKET:
        raise RocketError("Les agents Rocket ne peuvent pas se saboter entre eux.")


@transaction.atomic
def submit_night_action(game_id, user, target_id, expected_revision) -> RocketGame:
    game = RocketGame.objects.select_for_update().get(pk=game_id)
    actor = _player_for(game, user)
    _assert_revision(game, expected_revision)
    if game.status != RocketGame.Status.NUIT:
        raise RocketError("La nuit est déjà terminée.")
    if not actor.is_alive:
        raise RocketPermissionError("Un joueur éliminé ne peut plus agir.")

    kind = _action_kind(actor.role)
    if kind is None:
        raise RocketPermissionError("Ton rôle n'a pas d'action nocturne.")
    try:
        target = game.players.get(pk=target_id)
    except (RocketPlayer.DoesNotExist, TypeError, ValueError):
        raise RocketError("Cible inconnue.") from None
    _check_target(actor, target, kind)

    action, _ = RocketNightAction.objects.update_or_create(
        game=game,
        actor=actor,
        round_number=game.round_number,
        kind=kind,
        defaults={"target": target, "result_is_rocket": None},
    )
    if kind == RocketNightAction.Kind.INSPECT:
        action.result_is_rocket = target.role == RocketPlayer.Role.ROCKET
        action.save(update_fields=["result_is_rocket"])
    _bump(game)
    _resolve_night_if_ready(game)
    return game


def _night_actors(game: RocketGame) -> list[RocketPlayer]:
    actionable = {
        RocketPlayer.Role.ROCKET,
        RocketPlayer.Role.DETECTIVE,
        RocketPlayer.Role.GUARDIAN,
    }
    return list(game.players.filter(is_alive=True, role__in=actionable).order_by("turn_order"))


def _resolve_night_if_ready(game: RocketGame) -> bool:
    actors = _night_actors(game)
    submitted = set(
        game.night_actions.filter(round_number=game.round_number).values_list("actor_id", flat=True)
    )
    if any(actor.pk not in submitted for actor in actors):
        return False

    actions = list(game.night_actions.filter(round_number=game.round_number).select_related("target"))
    kill_actions = [action for action in actions if action.kind == RocketNightAction.Kind.KILL]
    protected_id = next(
        (action.target_id for action in actions if action.kind == RocketNightAction.Kind.PROTECT),
        None,
    )

    victim = None
    if kill_actions:
        counts = Counter(action.target_id for action in kill_actions)
        top = max(counts.values())
        tied_ids = {target_id for target_id, count in counts.items() if count == top}
        victim = game.players.filter(pk__in=tied_ids).order_by("turn_order").first()

    protected = bool(victim and victim.pk == protected_id)
    if victim is not None and not protected:
        victim.is_alive = False
        victim.save(update_fields=["is_alive"])

    game.last_event = {
        "kind": "night",
        "round": game.round_number,
        "victim_id": victim.pk if victim and not protected else None,
        "attack_blocked": protected,
    }
    if _finish_if_won(game):
        return True
    game.status = RocketGame.Status.DISCUSSION
    game.phase_deadline = timezone.now() + timedelta(seconds=DISCUSSION_SECONDS)
    _bump(game, "status", "last_event", "phase_deadline")
    return True


@transaction.atomic
def start_vote(game_id, user, expected_revision) -> RocketGame:
    game = RocketGame.objects.select_for_update().get(pk=game_id)
    _assert_revision(game, expected_revision)
    player = _player_for(game, user)
    if not player.is_alive:
        raise RocketPermissionError("Seul un survivant peut ouvrir le conseil.")
    if game.status != RocketGame.Status.DISCUSSION:
        raise RocketError("Le conseil ne peut pas commencer maintenant.")
    game.status = RocketGame.Status.VOTE
    game.phase_deadline = timezone.now() + timedelta(seconds=VOTE_SECONDS)
    _bump(game, "status", "phase_deadline")
    return game


@transaction.atomic
def submit_vote(game_id, user, target_id, expected_revision) -> RocketGame:
    game = RocketGame.objects.select_for_update().get(pk=game_id)
    voter = _player_for(game, user)
    _assert_revision(game, expected_revision)
    if game.status != RocketGame.Status.VOTE:
        raise RocketError("Le vote n'est pas ouvert.")
    if not voter.is_alive:
        raise RocketPermissionError("Un joueur éliminé ne vote plus.")
    try:
        target = game.players.get(pk=target_id, is_alive=True)
    except (RocketPlayer.DoesNotExist, TypeError, ValueError):
        raise RocketError("Cible de vote inconnue.") from None
    if target.pk == voter.pk:
        raise RocketError("Tu ne peux pas voter contre toi-même.")

    RocketVote.objects.update_or_create(
        game=game,
        voter=voter,
        round_number=game.round_number,
        defaults={"target": target},
    )
    _bump(game)
    _resolve_vote_if_ready(game)
    return game


def _resolve_vote_if_ready(game: RocketGame, *, force=False) -> bool:
    alive_ids = set(game.players.filter(is_alive=True).values_list("pk", flat=True))
    ballots = list(game.votes.filter(round_number=game.round_number, voter_id__in=alive_ids))
    if not force and len({ballot.voter_id for ballot in ballots}) < len(alive_ids):
        return False

    counts = Counter(ballot.target_id for ballot in ballots)
    top = max(counts.values()) if counts else 0
    leaders = [target_id for target_id, count in counts.items() if count == top]
    eliminated = game.players.filter(pk=leaders[0]).first() if len(leaders) == 1 else None
    if eliminated is not None:
        eliminated.is_alive = False
        eliminated.save(update_fields=["is_alive"])

    game.last_event = {
        "kind": "vote",
        "round": game.round_number,
        "eliminated_id": eliminated.pk if eliminated else None,
        "tie": eliminated is None,
        "counts": {str(player_id): count for player_id, count in counts.items()},
    }
    if _finish_if_won(game):
        return True
    game.status = RocketGame.Status.NUIT
    game.round_number += 1
    game.phase_deadline = timezone.now() + timedelta(seconds=NIGHT_SECONDS)
    _bump(game, "status", "round_number", "last_event", "phase_deadline")
    return True


def _finish_if_won(game: RocketGame) -> bool:
    alive = game.players.filter(is_alive=True)
    rockets = alive.filter(role=RocketPlayer.Role.ROCKET).count()
    allies = alive.exclude(role=RocketPlayer.Role.ROCKET).count()
    if rockets > 0 and rockets < allies:
        return False

    winner = RocketGame.WinnerSide.ALLIES if rockets == 0 else RocketGame.WinnerSide.ROCKET
    game.status = RocketGame.Status.TERMINEE
    game.winner_side = winner
    game.finished_at = timezone.now()
    game.phase_deadline = None
    _bump(game, "status", "winner_side", "finished_at", "last_event", "phase_deadline")

    players = list(game.players.select_related("user"))
    winner_user_ids = [
        player.user_id
        for player in players
        if (winner == RocketGame.WinnerSide.ROCKET) == (player.role == RocketPlayer.Role.ROCKET)
    ]
    record_completed_game((player.user for player in players), winner_user_ids)
    return True


@transaction.atomic
def send_message(game_id, user, body, expected_revision) -> RocketMessage:
    game = RocketGame.objects.select_for_update().get(pk=game_id)
    player = _player_for(game, user)
    _assert_revision(game, expected_revision)
    if game.status != RocketGame.Status.DISCUSSION:
        raise RocketError("Le canal s'ouvre uniquement pendant la discussion.")
    if not player.is_alive:
        raise RocketPermissionError("Les joueurs éliminés observent le débat en silence.")
    if not isinstance(body, str):
        raise RocketError("Message invalide.")
    body = " ".join(body.split()).strip()
    if not body:
        raise RocketError("Écris un message avant de l'envoyer.")
    if len(body) > MAX_MESSAGE_LENGTH:
        raise RocketError(f"Le message ne peut pas dépasser {MAX_MESSAGE_LENGTH} caractères.")
    sequence = (game.messages.aggregate(top=Max("sequence"))["top"] or 0) + 1
    message = RocketMessage.objects.create(
        game=game,
        player=player,
        round_number=game.round_number,
        sequence=sequence,
        body=body,
    )
    _bump(game)
    return message


@transaction.atomic
def advance_if_expired(game_id) -> RocketGame:
    """Garantit qu'une absence réseau ne bloque jamais durablement une partie."""

    game = RocketGame.objects.select_for_update().get(pk=game_id)
    if (
        game.status in {RocketGame.Status.EN_ATTENTE, RocketGame.Status.TERMINEE}
        or game.phase_deadline is None
        or timezone.now() < game.phase_deadline
    ):
        return game

    if game.status == RocketGame.Status.DISCUSSION:
        game.status = RocketGame.Status.VOTE
        game.phase_deadline = timezone.now() + timedelta(seconds=VOTE_SECONDS)
        _bump(game, "status", "phase_deadline")
        return game

    if game.status == RocketGame.Status.VOTE:
        _resolve_vote_if_ready(game, force=True)
        return game

    if game.status != RocketGame.Status.NUIT:
        return game

    if _finish_if_won(game):
        return game

    actors = _night_actors(game)
    submitted_ids = set(
        game.night_actions.filter(round_number=game.round_number).values_list("actor_id", flat=True)
    )
    alive = list(game.players.filter(is_alive=True).order_by("turn_order"))
    for actor in actors:
        if actor.pk in submitted_ids:
            continue
        kind = _action_kind(actor.role)
        candidates = [player for player in alive if player.pk != actor.pk]
        if kind == RocketNightAction.Kind.KILL:
            candidates = [player for player in candidates if player.role != RocketPlayer.Role.ROCKET]
        elif kind == RocketNightAction.Kind.PROTECT:
            candidates = alive
        if not candidates:
            continue
        target = candidates[0]
        action = RocketNightAction.objects.create(
            game=game,
            actor=actor,
            target=target,
            round_number=game.round_number,
            kind=kind,
        )
        if kind == RocketNightAction.Kind.INSPECT:
            action.result_is_rocket = target.role == RocketPlayer.Role.ROCKET
            action.save(update_fields=["result_is_rocket"])
    _resolve_night_if_ready(game)
    return game


def _role_payload(role: str) -> dict:
    presentation = ROLE_PRESENTATION[role]
    return {
        "key": role,
        "name": presentation["name"],
        "side": presentation["side"],
        "mission": presentation["mission"],
        "artwork_url": static(presentation["artwork"]),
    }


def _last_event_payload(game: RocketGame, players_by_id: dict[int, RocketPlayer]) -> dict:
    payload = dict(game.last_event or {})
    for source, destination in (("victim_id", "victim_name"), ("eliminated_id", "eliminated_name")):
        player = players_by_id.get(payload.get(source))
        payload[destination] = player.user.get_username() if player else ""
    return payload


def serialize_game_state(game: RocketGame, user) -> dict:
    players = list(game.players.select_related("user").order_by("turn_order"))
    players_by_id = {player.pk: player for player in players}
    me = next((player for player in players if player.user_id == user.id), None)
    if me is None:
        raise RocketPermissionError("Vous ne participez pas à cette infiltration.")

    reveal_all = game.status == RocketGame.Status.TERMINEE
    rocket_knows_team = me.role == RocketPlayer.Role.ROCKET and game.status != RocketGame.Status.EN_ATTENTE

    serialized_players = []
    for player in players:
        visible_role = None
        if (
            reveal_all
            or player.pk == me.pk
            or (rocket_knows_team and player.role == RocketPlayer.Role.ROCKET)
        ):
            visible_role = _role_payload(player.role) if player.role else None
        serialized_players.append(
            {
                "id": player.pk,
                "username": player.user.get_username(),
                "turn_order": player.turn_order,
                "is_alive": player.is_alive,
                "is_host": player.user_id == game.created_by_id,
                "is_me": player.pk == me.pk,
                "role": visible_role,
            }
        )

    current_actions = game.night_actions.filter(round_number=game.round_number)
    own_action = current_actions.filter(actor=me).select_related("target").first()
    detective_results = []
    if me.role == RocketPlayer.Role.DETECTIVE:
        detective_results = [
            {
                "round": action.round_number,
                "target_id": action.target_id,
                "target_name": action.target.user.get_username(),
                "is_rocket": action.result_is_rocket,
            }
            for action in game.night_actions.filter(
                actor=me,
                kind=RocketNightAction.Kind.INSPECT,
                result_is_rocket__isnull=False,
            ).select_related("target__user")
        ]

    current_votes = game.votes.filter(round_number=game.round_number)
    own_vote = current_votes.filter(voter=me).first()
    messages = [
        {
            "sequence": message.sequence,
            "round": message.round_number,
            "player_id": message.player_id,
            "username": message.player.user.get_username(),
            "body": message.body,
            "created_at": message.created_at.isoformat(),
        }
        for message in game.messages.select_related("player__user")
    ]

    my_role = _role_payload(me.role) if me.role else None
    action_kind = _action_kind(me.role) if me.role else None
    state = {
        "game": {
            "id": str(game.id),
            "status": game.status,
            "status_label": game.get_status_display(),
            "round": game.round_number,
            "turn_revision": game.turn_revision,
            "min_players": MIN_PLAYERS,
            "max_players": game.max_players,
            "host_id": game.created_by_id,
            "winner_side": game.winner_side,
            "winner_label": game.get_winner_side_display() if game.winner_side else "",
            "phase_deadline": game.phase_deadline.isoformat() if game.phase_deadline else None,
            "last_event": _last_event_payload(game, players_by_id),
        },
        "players": serialized_players,
        "me": {
            "id": me.pk,
            "username": me.user.get_username(),
            "is_alive": me.is_alive,
            "is_host": me.user_id == game.created_by_id,
            "role": my_role,
            "team_won": (
                None
                if not game.winner_side
                else (game.winner_side == RocketGame.WinnerSide.ROCKET)
                == (me.role == RocketPlayer.Role.ROCKET)
            ),
            "night_action_kind": action_kind,
            "night_action_target_id": own_action.target_id if own_action else None,
            "vote_target_id": own_vote.target_id if own_vote else None,
        },
        "night": {
            "own_submitted": own_action is not None,
            "detective_results": detective_results,
        },
        "vote": {
            "own_submitted": own_vote is not None,
            "submitted": current_votes.count(),
            "required": sum(1 for player in players if player.is_alive),
        },
        "messages": messages,
    }
    return state


def get_lobby_state(user) -> dict:
    open_games = RocketGame.objects.filter(status=RocketGame.Status.EN_ATTENTE).select_related("created_by")
    open_rows = []
    for game in open_games:
        count = game.players.count()
        open_rows.append(
            {
                "id": str(game.id),
                "host": game.created_by.get_username(),
                "player_count": count,
                "max_players": game.max_players,
                "can_join": count < game.max_players and not game.players.filter(user=user).exists(),
            }
        )
    my_games = [
        {
            "id": str(game.id),
            "status": game.status,
            "status_label": game.get_status_display(),
            "round": game.round_number,
        }
        for game in RocketGame.objects.filter(players__user=user).exclude(status=RocketGame.Status.EN_ATTENTE)
    ]
    return {"open_games": open_rows, "my_games": my_games}
