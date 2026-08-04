"""Moteur de jeu Poké-Uno, isolé des vues Django (SRP).

Ne dépend que de l'ORM et de la bibliothèque standard : testable en pur
Python, sans requête HTTP ni session. Toute la logique métier (distribution,
validation des coups, tour par tour, fin de partie) vit ici ; les vues se
contentent d'appeler ces méthodes et de traduire les exceptions en réponses
HTTP.
"""

import random
from datetime import timedelta

from django.db.models import F, Max
from django.utils import timezone

from game.card_actions import assign_actions
from game.deck_builder import draw_game_types, select_species, species_type_slugs
from game.models import Game, GameCard, GamePlayer, MoveLog, PokemonCard, PokemonType, Profile
from game.pokemon_types import get_pokemon_type
from game.quests import EVENT_GAME_PLAYED, EVENT_GAME_WON, record_event

HAND_SIZE = 7
DECK_COPIES_PER_CARD = 2
NORMAL_CARD_POINTS = 10
LEGENDARY_CARD_POINTS = 25
MIN_PLAYERS = 2
WAITING_ROOM_TIMEOUT = timedelta(minutes=15)
TURN_INACTIVITY_TIMEOUT = timedelta(minutes=5)
DRAW_PENALTIES = {
    GameCard.Action.DRAW_TWO: 2,
    GameCard.Action.DRAW_FOUR: 4,
}
BOT_NAMES = ("IA Porygon", "IA Motisma", "IA Lucario", "IA Mimiqui", "IA Métalosse")


class GameEngineError(Exception):
    """Erreur métier du moteur de jeu."""


class GameNotJoinableError(GameEngineError):
    pass


class GameFullError(GameEngineError):
    pass


class NotEnoughPlayersError(GameEngineError):
    pass


class NotYourTurnError(GameEngineError):
    pass


class InvalidMoveError(GameEngineError):
    pass


def card_point_value(pokemon_card: PokemonCard) -> int:
    """Valeur en points d'une carte, utilisée pour le score de fin de partie."""
    return LEGENDARY_CARD_POINTS if pokemon_card.is_legendary else NORMAL_CARD_POINTS


def close_stale_games() -> None:
    """Ferme les parties abandonnées : appelé à chaque accès au lobby ou à une
    partie, sans tâche planifiée dédiée, pour rester dans le périmètre de
    cette plateforme (pas de worker Celery/cron).

    Deux critères indépendants : un salon d'attente jamais démarré au bout de
    ``WAITING_ROOM_TIMEOUT``, ou une partie en cours sans le moindre coup
    (carte jouée, pioche...) depuis ``TURN_INACTIVITY_TIMEOUT``.
    """
    now = timezone.now()

    Game.objects.filter(
        status=Game.Status.EN_ATTENTE,
        created_at__lt=now - WAITING_ROOM_TIMEOUT,
    ).update(status=Game.Status.TERMINEE, finished_at=now)

    stale_active_games = (
        Game.objects.filter(status=Game.Status.EN_COURS)
        .annotate(last_activity_at=Max("move_logs__created_at"))
        .filter(last_activity_at__lt=now - TURN_INACTIVITY_TIMEOUT)
    )

    for game in stale_active_games:
        game.status = Game.Status.TERMINEE
        game.finished_at = now
        game.save(update_fields=["status", "finished_at"])
        MoveLog.objects.create(game=game, move_type=MoveLog.MoveType.ABANDON)


class GameEngine:
    def __init__(self, game: Game):
        self.game = game

    # -- Lobby -----------------------------------------------------------

    def add_player(self, user) -> GamePlayer:
        if self.game.status != Game.Status.EN_ATTENTE:
            raise GameNotJoinableError("La partie a déjà commencé.")
        if self.game.players.filter(user=user).exists():
            return self.game.players.get(user=user)
        if self.game.players.count() >= self.game.max_players:
            raise GameFullError("La partie est complète.")

        turn_order = self.game.players.count()
        return GamePlayer.objects.create(game=self.game, user=user, turn_order=turn_order)

    def add_bot(self) -> GamePlayer:
        if self.game.status != Game.Status.EN_ATTENTE:
            raise GameNotJoinableError("La partie a déjà commencé.")
        if self.game.players.count() >= self.game.max_players:
            raise GameFullError("La partie est complète.")

        used_names = set(self.game.players.exclude(bot_name="").values_list("bot_name", flat=True))
        bot_name = next((name for name in BOT_NAMES if name not in used_names), None)
        if bot_name is None:
            suffix = 1
            while f"IA {suffix}" in used_names:
                suffix += 1
            bot_name = f"IA {suffix}"
        return GamePlayer.objects.create(
            game=self.game,
            user=None,
            bot_name=bot_name,
            turn_order=self.game.players.count(),
        )

    def remove_bot(self, player_id: int):
        if self.game.status != Game.Status.EN_ATTENTE:
            raise GameNotJoinableError("La partie a déjà commencé.")
        bot = self.game.players.filter(pk=player_id, user__isnull=True).first()
        if bot is None:
            raise GameEngineError("Cette IA n'existe pas dans ce salon.")

        removed_order = bot.turn_order
        bot.delete()
        for player in self.game.players.filter(turn_order__gt=removed_order).order_by("turn_order"):
            player.turn_order -= 1
            player.save(update_fields=["turn_order"])

    # -- Démarrage & distribution -----------------------------------------

    def build_deck(self, rng=None) -> list[PokemonType]:
        """Tire les types de la partie puis la pioche correspondante.

        Renvoie les types tirés, dans l'ordre du tirage : c'est cet ordre que
        l'animation de démarrage rejoue côté navigateur.
        """
        rng = rng or random
        catalogue = list(
            PokemonCard.objects.filter(in_current_deck=True).select_related("primary_type", "secondary_type")
        )
        type_slugs = draw_game_types(catalogue, rng)
        species = select_species(catalogue, type_slugs, rng)
        actions = assign_actions(species, rng)

        physical_cards = [card for card in species for _ in range(DECK_COPIES_PER_CARD)]
        rng.shuffle(physical_cards)

        GameCard.objects.bulk_create(
            [
                GameCard(
                    game=self.game,
                    pokemon_card=pokemon_card,
                    location=GameCard.Location.PIOCHE,
                    action=actions.get(pokemon_card.pk, GameCard.Action.NORMAL),
                    order_index=self.game.next_card_sequence(),
                )
                for pokemon_card in physical_cards
            ]
        )

        types_by_slug = {t.slug: t for t in PokemonType.objects.filter(slug__in=type_slugs)}
        selected_types = [types_by_slug[slug] for slug in type_slugs if slug in types_by_slug]
        self.game.selected_types.set(selected_types)
        return selected_types

    def start_game(self):
        if self.game.status != Game.Status.EN_ATTENTE:
            raise GameNotJoinableError("La partie a déjà commencé.")

        players = list(self.game.players.all())
        if len(players) < MIN_PLAYERS:
            raise NotEnoughPlayersError(f"Il faut au moins {MIN_PLAYERS} joueurs.")

        self.build_deck()
        MoveLog.objects.create(game=self.game, move_type=MoveLog.MoveType.DEBUT_PARTIE)

        for player in players:
            for _ in range(HAND_SIZE):
                self._draw_top_of_pile(player)
        MoveLog.objects.create(game=self.game, move_type=MoveLog.MoveType.DISTRIBUTION)

        # La première défausse n'a aucun effet : la partie commence sans type
        # à déclarer, pénalité à distribuer ou sens à inverser.
        starter = self._draw_top_of_pile(owner=None)
        while starter.pokemon_card.is_legendary or starter.action != GameCard.Action.NORMAL:
            starter.location = GameCard.Location.PIOCHE
            starter.order_index = self.game.next_card_sequence()
            starter.save(update_fields=["location", "order_index"])
            starter = self._draw_top_of_pile(owner=None)
        starter.location = GameCard.Location.DEFAUSSE
        starter.save(update_fields=["location"])

        self.game.status = Game.Status.EN_COURS
        self.game.started_at = timezone.now()
        self.game.current_turn_number = 0
        self.game.turn_revision = 1
        self.game.active_type = None
        self.game.save(
            update_fields=[
                "status",
                "started_at",
                "current_turn_number",
                "turn_revision",
                "active_type",
                "card_sequence_counter",
            ]
        )

    def _draw_top_of_pile(self, owner) -> GameCard:
        """Retire la carte du dessus de la pioche (remélange si épuisée) et la place en MAIN (ou laisse en transit si owner=None)."""
        top = (
            GameCard.objects.filter(game=self.game, location=GameCard.Location.PIOCHE)
            .order_by("order_index")
            .first()
        )
        if top is None:
            self.reshuffle_discard_into_draw()
            top = (
                GameCard.objects.filter(game=self.game, location=GameCard.Location.PIOCHE)
                .order_by("order_index")
                .first()
            )
        if top is None:
            raise GameEngineError("Plus aucune carte disponible, ni en pioche ni en défausse.")

        if owner is not None:
            top.location = GameCard.Location.MAIN
            top.owner = owner
            top.order_index = self.game.next_card_sequence()
            top.save(update_fields=["location", "owner", "order_index"])
        return top

    def reshuffle_discard_into_draw(self):
        """Remélange la défausse (sauf la carte du dessus) dans la pioche."""
        top_discard = self.get_top_discard()
        to_reshuffle = GameCard.objects.filter(game=self.game, location=GameCard.Location.DEFAUSSE).exclude(
            pk=top_discard.pk if top_discard else None
        )

        ids = list(to_reshuffle.values_list("pk", flat=True))
        random.shuffle(ids)
        for card_id in ids:
            GameCard.objects.filter(pk=card_id).update(
                location=GameCard.Location.PIOCHE,
                owner=None,
                order_index=self.game.next_card_sequence(),
            )
        self.game.save(update_fields=["card_sequence_counter"])
        MoveLog.objects.create(game=self.game, move_type=MoveLog.MoveType.MELANGE_DEFAUSSE)

    # -- État de la partie -------------------------------------------------

    def get_top_discard(self) -> GameCard | None:
        return (
            GameCard.objects.filter(game=self.game, location=GameCard.Location.DEFAUSSE)
            .order_by("-order_index")
            .first()
        )

    def get_current_player(self) -> GamePlayer:
        return self.game.players.get(turn_order=self.game.current_turn_number)

    # -- Validation & coups --------------------------------------------------

    def is_move_valid(self, player: GamePlayer, game_card: GameCard) -> tuple[bool, str | None]:
        if self.game.status != Game.Status.EN_COURS:
            return False, "La partie n'est pas en cours."
        if self.get_current_player().pk != player.pk:
            return False, "Ce n'est pas votre tour."
        if game_card.location != GameCard.Location.MAIN or game_card.owner_id != player.pk:
            return False, "Cette carte n'est pas dans votre main."

        pokemon_card = game_card.pokemon_card
        if self.requires_type_choice(game_card):
            return True, None

        top_discard = self.get_top_discard()
        if top_discard is None:
            return True, None

        card_types = set(species_type_slugs(pokemon_card))
        # Un joker a imposé un type : lui seul compte, quels que soient les
        # types de la carte posée dessus.
        if self.game.active_type_id:
            if self.game.active_type.slug in card_types:
                return True, None
            return False, "Un joker a imposé un type : jouez une carte de ce type."

        if card_types & set(species_type_slugs(top_discard.pokemon_card)):
            return True, None
        if pokemon_card.pokedex_id == top_discard.pokemon_card.pokedex_id:
            return True, None

        return False, "Cette carte ne partage aucun type ni l'espèce de la carte du dessus."

    def play_card(
        self,
        player: GamePlayer,
        game_card: GameCard,
        declared_type_slug: str | None = None,
    ) -> GameCard:
        ok, reason = self.is_move_valid(player, game_card)
        if not ok:
            if self.get_current_player().pk != player.pk:
                raise NotYourTurnError(reason)
            raise InvalidMoveError(reason)

        if self.requires_type_choice(game_card):
            declared_type = self.get_selected_types().filter(slug=declared_type_slug).first()
            if declared_type is None:
                raise InvalidMoveError("Cette carte impose de choisir un des types de la partie.")
            self.game.active_type = declared_type
        else:
            declared_type = None
            self.game.active_type = None
        game_card.location = GameCard.Location.DEFAUSSE
        game_card.owner = None
        game_card.order_index = self.game.next_card_sequence()
        game_card.save(update_fields=["location", "owner", "order_index"])
        self.game.save(
            update_fields=[
                "active_type",
                "card_sequence_counter",
            ]
        )

        MoveLog.objects.create(
            game=self.game,
            player=player,
            move_type=MoveLog.MoveType.JOUER_CARTE,
            game_card=game_card,
            declared_type=declared_type,
        )

        self._apply_card_action(player, game_card.action)

        if not GameCard.objects.filter(
            game=self.game, location=GameCard.Location.MAIN, owner=player
        ).exists():
            self.end_game(winner=player)

        return game_card

    def get_selected_types(self):
        """Les types tirés au démarrage, dans un ordre d'affichage stable."""
        return self.game.selected_types.order_by("name_fr")

    @staticmethod
    def requires_type_choice(game_card: GameCard) -> bool:
        """Un joker : légendaire ou +4. Il impose le type du tour suivant."""
        return game_card.pokemon_card.is_legendary or game_card.action == GameCard.Action.DRAW_FOUR

    def _apply_card_action(self, player: GamePlayer, action: str):
        """Applique l'effet puis place le curseur sur le prochain joueur.

        Un +2/+4 fait piocher et saute la cible. Un bouclier déjà actif annule
        entièrement cette pénalité, est consommé, et laisse la cible jouer.
        """
        if action == GameCard.Action.SHIELD:
            player.has_protection = True
            player.save(update_fields=["has_protection"])
            self.advance_turn()
            return

        if action == GameCard.Action.REVERSE:
            self.game.direction = -1 if self.game.direction > 0 else 1
            self.game.save(update_fields=["direction"])
            self.advance_turn()
            return

        draw_count = DRAW_PENALTIES.get(action)
        if draw_count is None:
            self.advance_turn()
            return

        target = self._get_player_at_offset(1)
        if target.has_protection:
            target.has_protection = False
            target.save(update_fields=["has_protection"])
            self.advance_turn()
            return

        for _ in range(draw_count):
            self._draw_top_of_pile(target)
        self.game.save(update_fields=["card_sequence_counter"])
        MoveLog.objects.create(
            game=self.game,
            player=target,
            move_type=MoveLog.MoveType.PIOCHER,
        )
        self.advance_turn(steps=2)

    def draw_card(self, player: GamePlayer, count: int = 1) -> list[GameCard]:
        if self.game.status != Game.Status.EN_COURS:
            raise InvalidMoveError("La partie n'est pas en cours.")
        if self.get_current_player().pk != player.pk:
            raise NotYourTurnError("Ce n'est pas votre tour.")

        drawn = [self._draw_top_of_pile(player) for _ in range(count)]
        self.game.save(update_fields=["card_sequence_counter"])
        MoveLog.objects.create(game=self.game, player=player, move_type=MoveLog.MoveType.PIOCHER)
        self.advance_turn()
        return drawn

    def _get_player_at_offset(self, offset: int) -> GamePlayer:
        player_count = self.game.players.count()
        turn_order = (self.game.current_turn_number + (self.game.direction * offset)) % player_count
        return self.game.players.get(turn_order=turn_order)

    def advance_turn(self, steps: int = 1):
        player_count = self.game.players.count()
        self.game.current_turn_number = (
            self.game.current_turn_number + (self.game.direction * steps)
        ) % player_count
        self.game.turn_revision += 1
        self.game.save(update_fields=["current_turn_number", "turn_revision"])

    # -- Fin de partie -------------------------------------------------------

    def end_game(self, winner: GamePlayer):
        self.game.status = Game.Status.TERMINEE
        self.game.finished_at = timezone.now()
        self.game.save(update_fields=["status", "finished_at"])

        won_points = sum(
            card_point_value(game_card.pokemon_card)
            for game_card in GameCard.objects.select_related("pokemon_card")
            .filter(game=self.game, location=GameCard.Location.MAIN)
            .exclude(owner=winner)
        )
        winner.score += won_points
        winner.save(update_fields=["score"])

        for game_player in self.game.players.filter(user__isnull=False):
            profile, _ = Profile.objects.get_or_create(user=game_player.user)
            increments = {"total_games_played": F("total_games_played") + 1}
            if game_player.pk == winner.pk:
                increments["total_games_won"] = F("total_games_won") + 1
            Profile.objects.filter(pk=profile.pk).update(**increments)
            record_event(game_player.user, EVENT_GAME_PLAYED)
            if game_player.pk == winner.pk:
                record_event(game_player.user, EVENT_GAME_WON)

        MoveLog.objects.create(game=self.game, player=winner, move_type=MoveLog.MoveType.FIN_PARTIE)

    # -- Sérialisation pour le polling front ---------------------------------

    def get_game_state(self, for_player: GamePlayer) -> dict:
        """État de la partie pour le joueur demandeur. Ne renvoie JAMAIS la
        main d'un adversaire (seulement son nombre de cartes) : cette règle
        vit ici, dans le moteur, pour rester garantie quel que soit l'endpoint
        qui appelle get_game_state."""
        top_discard = (
            GameCard.objects.select_related("pokemon_card__primary_type", "pokemon_card__secondary_type")
            .filter(game=self.game, location=GameCard.Location.DEFAUSSE)
            .order_by("-order_index")
            .first()
        )
        players = list(self.game.players.select_related("user").all())
        current_player = (
            next((gp for gp in players if gp.turn_order == self.game.current_turn_number), None)
            if self.game.status == Game.Status.EN_COURS
            else None
        )

        # Une seule requête récupère toutes les mains, y compris leurs types.
        # L'ancien code faisait une requête par adversaire à chaque poll, ce qui
        # rendait le plateau inutilement lent dès qu'une partie comptait 5-6 joueurs.
        hand_cards_by_owner = {gp.pk: [] for gp in players}
        for game_card in (
            GameCard.objects.select_related("pokemon_card__primary_type", "pokemon_card__secondary_type")
            .filter(game=self.game, location=GameCard.Location.MAIN)
            .order_by("order_index")
        ):
            hand_cards_by_owner[game_card.owner_id].append(game_card)

        def serialize_type(pokemon_type):
            info = get_pokemon_type(pokemon_type.slug)
            return {
                "slug": pokemon_type.slug,
                "name_fr": info.name_fr if info else pokemon_type.name_fr,
                "color": info.color if info else "#9fa19f",
            }

        def serialize_card(game_card):
            pc = game_card.pokemon_card
            return {
                "id": game_card.id,
                "pokedex_id": pc.pokedex_id,
                "name_fr": pc.name_fr,
                "name_en": pc.name_en,
                "sprite_url": pc.sprite_url,
                "types": [serialize_type(pokemon_type) for pokemon_type in pc.types],
                "is_legendary": pc.is_legendary,
                "requires_type_choice": self.requires_type_choice(game_card),
                "action": game_card.action,
                "action_label": game_card.get_action_display(),
            }

        players_payload = []
        for gp in players:
            entry = {
                "id": gp.id,
                "username": gp.display_name,
                "is_bot": gp.is_bot,
                "turn_order": gp.turn_order,
                "score": gp.score,
                "has_protection": gp.has_protection,
                "is_current_turn": current_player is not None and current_player.pk == gp.pk,
            }
            if gp.pk == for_player.pk:
                entry["hand"] = [serialize_card(gc) for gc in hand_cards_by_owner[gp.pk]]
            else:
                entry["hand_count"] = len(hand_cards_by_owner[gp.pk])
            players_payload.append(entry)

        return {
            "game_id": str(self.game.id),
            "status": self.game.status,
            "max_players": self.game.max_players,
            "is_creator": self.game.created_by_id == for_player.user_id,
            "direction": self.game.direction,
            "turn_revision": self.game.turn_revision,
            "active_type": serialize_type(self.game.active_type) if self.game.active_type_id else None,
            "game_types": [serialize_type(pokemon_type) for pokemon_type in self.get_selected_types()],
            "top_discard": serialize_card(top_discard) if top_discard else None,
            "draw_pile_count": GameCard.objects.filter(
                game=self.game, location=GameCard.Location.PIOCHE
            ).count(),
            "is_my_turn": current_player is not None and current_player.pk == for_player.pk,
            "players": players_payload,
        }
