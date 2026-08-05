import uuid

from django.conf import settings
from django.db import models


class Game(models.Model):
    """Une course de deux à quatre dresseurs."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EN_ATTENTE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="starterrace_created_games",
    )
    current_turn = models.ForeignKey(
        "Player",
        on_delete=models.SET_NULL,
        related_name="current_turn_games",
        null=True,
        blank=True,
    )
    winner = models.ForeignKey(
        "Player",
        on_delete=models.SET_NULL,
        related_name="won_starterrace_games",
        null=True,
        blank=True,
    )
    pending_roll = models.PositiveSmallIntegerField(null=True, blank=True)
    turn_revision = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pending_roll__isnull=True)
                | models.Q(pending_roll__gte=1, pending_roll__lte=6),
                name="starterrace_pending_roll_one_to_six",
            )
        ]

    @property
    def min_players(self):
        return 2

    @property
    def max_players(self):
        return 4

    def __str__(self):
        return f"Course {self.id} ({self.get_status_display()})"


class Player(models.Model):
    """Un dresseur, sa place autour du plateau et son starter officiel."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="starterrace_participations",
        null=True,
        blank=True,
    )
    bot_name = models.CharField(max_length=40, blank=True, default="")
    starter_card = models.ForeignKey(
        "game.PokemonCard",
        on_delete=models.PROTECT,
        related_name="starterrace_players",
    )
    turn_order = models.PositiveSmallIntegerField()
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "user"],
                name="unique_starterrace_user_per_game",
            ),
            models.UniqueConstraint(
                fields=["game", "turn_order"],
                name="unique_starterrace_turn_order",
            ),
            models.UniqueConstraint(
                fields=["game", "bot_name"],
                condition=~models.Q(bot_name=""),
                name="unique_starterrace_bot_name",
            ),
            models.CheckConstraint(
                condition=models.Q(turn_order__gte=0, turn_order__lte=3),
                name="starterrace_turn_order_zero_to_three",
            ),
            models.CheckConstraint(
                condition=(models.Q(user__isnull=False, bot_name=""))
                | (models.Q(user__isnull=True) & ~models.Q(bot_name="")),
                name="starterrace_player_has_one_controller",
            ),
        ]

    def __str__(self):
        return f"{self.display_name} · {self.starter_card.name_fr}"

    @property
    def is_bot(self):
        return self.user_id is None

    @property
    def display_name(self):
        return self.bot_name if self.is_bot else self.user.get_username()


class Pawn(models.Model):
    """Un des quatre pions d'un joueur.

    ``position`` est une progression depuis la case de départ du joueur :
    -1 est la maison, 0..39 la piste commune, 40..43 le couloir privé. La
    case 43 est la Ligue et rend le pion définitivement arrivé.
    """

    HOME = -1
    TRACK_LAST = 39
    FINISH = 43

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="pawns")
    number = models.PositiveSmallIntegerField()
    position = models.SmallIntegerField(default=HOME)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["player", "number"],
                name="unique_starterrace_pawn_number",
            ),
            models.CheckConstraint(
                condition=models.Q(number__gte=0, number__lte=3),
                name="starterrace_pawn_number_zero_to_three",
            ),
            models.CheckConstraint(
                # Les noms de la classe englobante ne sont pas visibles dans
                # le scope Python de ``Meta`` : garder ici les bornes SQL
                # explicites, documentées par ``HOME`` et ``FINISH`` plus haut.
                condition=models.Q(position__gte=-1, position__lte=43),
                name="starterrace_pawn_position_range",
            ),
        ]

    @property
    def is_home(self):
        return self.position == self.HOME

    @property
    def is_finished(self):
        return self.position == self.FINISH

    def __str__(self):
        return f"{self.player} · pion {self.number + 1}"


class Move(models.Model):
    """Historique public et immuable des déplacements résolus."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="moves")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="moves")
    pawn = models.ForeignKey(
        Pawn,
        on_delete=models.SET_NULL,
        related_name="moves",
        null=True,
        blank=True,
    )
    sequence = models.PositiveIntegerField()
    roll = models.PositiveSmallIntegerField()
    from_position = models.SmallIntegerField(null=True, blank=True)
    to_position = models.SmallIntegerField(null=True, blank=True)
    shortcut_from = models.PositiveSmallIntegerField(null=True, blank=True)
    shortcut_to = models.PositiveSmallIntegerField(null=True, blank=True)
    captured_pawns = models.JSONField(default=list, blank=True)
    was_pass = models.BooleanField(default=False)
    grants_extra_turn = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "sequence"],
                name="unique_starterrace_move_sequence",
            ),
            models.CheckConstraint(
                condition=models.Q(roll__gte=1, roll__lte=6),
                name="starterrace_move_roll_one_to_six",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        was_pass=True, pawn__isnull=True, from_position__isnull=True, to_position__isnull=True
                    )
                    | models.Q(
                        was_pass=False,
                        pawn__isnull=False,
                        from_position__isnull=False,
                        to_position__isnull=False,
                    )
                ),
                name="starterrace_move_payload_matches_pass",
            ),
        ]

    def __str__(self):
        action = "passe" if self.was_pass else f"pion {self.pawn_id}"
        return f"{self.sequence}. {self.player} lance {self.roll} et {action}"
