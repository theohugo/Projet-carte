"""Moteur de jeu Poké-Uno, isolé des vues Django (SRP).

Ne dépend que de l'ORM et de la bibliothèque standard : testable en pur
Python, sans requête HTTP ni session. Toute la logique métier (distribution,
validation des coups, tour par tour, fin de partie) vit ici ; les vues se
contentent d'appeler ces méthodes et de traduire les exceptions en réponses
HTTP.
"""

import random
from django.utils import timezone

from game.models import Game, GameCard, GamePlayer, MoveLog, PokemonCard, Profile

HAND_SIZE = 7
DECK_COPIES_PER_CARD = 2
NORMAL_CARD_POINTS = 10
LEGENDARY_CARD_POINTS = 25
MIN_PLAYERS = 2


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

    # -- Démarrage & distribution -----------------------------------------

    def build_deck(self):
        """Crée les GameCard (copies du catalogue) en pioche, ordre mélangé."""
        pokemon_cards = list(PokemonCard.objects.all())
        physical_cards = pokemon_cards * DECK_COPIES_PER_CARD
        random.shuffle(physical_cards)

        game_cards = []
        for pokemon_card in physical_cards:
            game_cards.append(
                GameCard(
                    game=self.game,
                    pokemon_card=pokemon_card,
                    location=GameCard.Location.PIOCHE,
                    order_index=self.game.next_card_sequence(),
                )
            )
        GameCard.objects.bulk_create(game_cards)

    def start_game(self):
        players = list(self.game.players.all())
        if len(players) < MIN_PLAYERS:
            raise NotEnoughPlayersError(f"Il faut au moins {MIN_PLAYERS} joueurs.")

        self.build_deck()
        MoveLog.objects.create(game=self.game, move_type=MoveLog.MoveType.DEBUT_PARTIE)

        for player in players:
            for _ in range(HAND_SIZE):
                self._draw_top_of_pile(player)
        MoveLog.objects.create(game=self.game, move_type=MoveLog.MoveType.DISTRIBUTION)

        # Première carte de la défausse : jamais une légendaire (elle exigerait
        # un type déclaré sans joueur pour le faire). On la ré-insère dans la
        # pioche avec un nouvel index tant que la carte piochée est légendaire.
        starter = self._draw_top_of_pile(owner=None)
        while starter.pokemon_card.is_legendary:
            starter.location = GameCard.Location.PIOCHE
            starter.order_index = self.game.next_card_sequence()
            starter.save(update_fields=["location", "order_index"])
            starter = self._draw_top_of_pile(owner=None)
        starter.location = GameCard.Location.DEFAUSSE
        starter.save(update_fields=["location"])

        self.game.status = Game.Status.EN_COURS
        self.game.started_at = timezone.now()
        self.game.current_turn_number = 0
        self.game.save(update_fields=["status", "started_at", "current_turn_number", "card_sequence_counter"])

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
        to_reshuffle = GameCard.objects.filter(
            game=self.game, location=GameCard.Location.DEFAUSSE
        ).exclude(pk=top_discard.pk if top_discard else None)

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
        if pokemon_card.is_legendary:
            return True, None

        top_discard = self.get_top_discard()
        if top_discard is None:
            return True, None

        effective_type_ids = (
            {self.game.active_type_id} if self.game.active_type_id else {t.id for t in top_discard.pokemon_card.types}
        )
        card_type_ids = {t.id for t in pokemon_card.types}
        if effective_type_ids & card_type_ids:
            return True, None
        if pokemon_card.pokedex_id == top_discard.pokemon_card.pokedex_id:
            return True, None

        return False, "Cette carte ne partage ni le type ni l'espèce de la carte du dessus."

    def play_card(self, player: GamePlayer, game_card: GameCard, declared_type=None) -> GameCard:
        ok, reason = self.is_move_valid(player, game_card)
        if not ok:
            if self.get_current_player().pk != player.pk:
                raise NotYourTurnError(reason)
            raise InvalidMoveError(reason)

        if game_card.pokemon_card.is_legendary:
            if declared_type is None:
                raise InvalidMoveError("Une carte légendaire impose de choisir le prochain type.")
            self.game.active_type = declared_type
        else:
            self.game.active_type = None

        game_card.location = GameCard.Location.DEFAUSSE
        game_card.owner = None
        game_card.order_index = self.game.next_card_sequence()
        game_card.save(update_fields=["location", "owner", "order_index"])
        self.game.save(update_fields=["active_type", "card_sequence_counter"])

        MoveLog.objects.create(
            game=self.game,
            player=player,
            move_type=MoveLog.MoveType.JOUER_CARTE,
            game_card=game_card,
            declared_type=declared_type,
        )

        if not GameCard.objects.filter(game=self.game, location=GameCard.Location.MAIN, owner=player).exists():
            self.end_game(winner=player)
        else:
            self.advance_turn()

        return game_card

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

    def advance_turn(self):
        player_count = self.game.players.count()
        self.game.current_turn_number = (self.game.current_turn_number + self.game.direction) % player_count
        self.game.save(update_fields=["current_turn_number"])

    # -- Fin de partie -------------------------------------------------------

    def end_game(self, winner: GamePlayer):
        self.game.status = Game.Status.TERMINEE
        self.game.finished_at = timezone.now()
        self.game.save(update_fields=["status", "finished_at"])

        for other in self.game.players.exclude(pk=winner.pk):
            points = sum(
                card_point_value(gc.pokemon_card)
                for gc in GameCard.objects.filter(game=self.game, location=GameCard.Location.MAIN, owner=other)
            )
            other.score += points
            other.save(update_fields=["score"])

        for game_player in self.game.players.all():
            profile, _ = Profile.objects.get_or_create(user=game_player.user)
            profile.total_games_played += 1
            if game_player.pk == winner.pk:
                profile.total_games_won += 1
            profile.save(update_fields=["total_games_played", "total_games_won"])

        MoveLog.objects.create(game=self.game, player=winner, move_type=MoveLog.MoveType.FIN_PARTIE)

    # -- Sérialisation pour le polling front ---------------------------------

    def get_game_state(self, for_player: GamePlayer) -> dict:
        """État de la partie pour le joueur demandeur. Ne renvoie JAMAIS la
        main d'un adversaire (seulement son nombre de cartes) : cette règle
        vit ici, dans le moteur, pour rester garantie quel que soit l'endpoint
        qui appelle get_game_state."""
        top_discard = self.get_top_discard()
        current_player = self.get_current_player() if self.game.status == Game.Status.EN_COURS else None

        def serialize_card(game_card):
            pc = game_card.pokemon_card
            return {
                "id": game_card.id,
                "pokedex_id": pc.pokedex_id,
                "name_fr": pc.name_fr,
                "name_en": pc.name_en,
                "sprite_url": pc.sprite_url,
                "primary_type": pc.primary_type.slug,
                "secondary_type": pc.secondary_type.slug if pc.secondary_type else None,
                "is_legendary": pc.is_legendary,
            }

        players_payload = []
        for gp in self.game.players.select_related("user").all():
            entry = {
                "id": gp.id,
                "username": gp.user.username,
                "turn_order": gp.turn_order,
                "score": gp.score,
                "is_current_turn": current_player is not None and current_player.pk == gp.pk,
            }
            if gp.pk == for_player.pk:
                entry["hand"] = [
                    serialize_card(gc)
                    for gc in GameCard.objects.filter(
                        game=self.game, location=GameCard.Location.MAIN, owner=gp
                    ).order_by("order_index")
                ]
            else:
                entry["hand_count"] = GameCard.objects.filter(
                    game=self.game, location=GameCard.Location.MAIN, owner=gp
                ).count()
            players_payload.append(entry)

        return {
            "game_id": str(self.game.id),
            "status": self.game.status,
            "active_type": self.game.active_type.slug if self.game.active_type else None,
            "top_discard": serialize_card(top_discard) if top_discard else None,
            "draw_pile_count": GameCard.objects.filter(
                game=self.game, location=GameCard.Location.PIOCHE
            ).count(),
            "is_my_turn": current_player is not None and current_player.pk == for_player.pk,
            "players": players_payload,
        }
