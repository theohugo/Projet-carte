import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class IslandGame(models.Model):
    """Une bataille navale Pokémon strictement limitée à deux joueurs."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        PLACEMENT = "PLACEMENT", "Placement"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.EN_ATTENTE,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="island_created_games",
    )
    current_turn = models.ForeignKey(
        "IslandPlayer",
        on_delete=models.SET_NULL,
        related_name="current_turn_games",
        null=True,
        blank=True,
    )
    winner = models.ForeignKey(
        "IslandPlayer",
        on_delete=models.SET_NULL,
        related_name="won_island_games",
        null=True,
        blank=True,
    )
    turn_revision = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def max_players(self):
        return 2

    def __str__(self):
        return f"Bataille des Îles {self.id} ({self.get_status_display()})"


class IslandPlayer(models.Model):
    game = models.ForeignKey(
        IslandGame,
        on_delete=models.CASCADE,
        related_name="players",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="island_participations",
    )
    turn_order = models.PositiveSmallIntegerField()
    is_ready = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "user"],
                name="unique_island_user_per_game",
            ),
            models.UniqueConstraint(
                fields=["game", "turn_order"],
                name="unique_island_turn_order",
            ),
            models.CheckConstraint(
                condition=Q(turn_order__in=(0, 1)),
                name="island_turn_order_zero_or_one",
            ),
        ]

    def __str__(self):
        return f"{self.user.get_username()} @ {self.game_id}"


class Formation(models.Model):
    """Un Pokémon aquatique occupe une ligne ou une colonne du plateau."""

    class Orientation(models.TextChoices):
        HORIZONTAL = "H", "Horizontale"
        VERTICAL = "V", "Verticale"

    player = models.ForeignKey(
        IslandPlayer,
        on_delete=models.CASCADE,
        related_name="formations",
    )
    pokemon_card = models.ForeignKey(
        "game.PokemonCard",
        on_delete=models.PROTECT,
        related_name="island_formations",
    )
    slot = models.PositiveSmallIntegerField()
    size = models.PositiveSmallIntegerField()
    start_row = models.PositiveSmallIntegerField(null=True, blank=True)
    start_col = models.PositiveSmallIntegerField(null=True, blank=True)
    orientation = models.CharField(
        max_length=1,
        choices=Orientation.choices,
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["slot"]
        constraints = [
            models.UniqueConstraint(
                fields=["player", "slot"],
                name="unique_island_formation_slot",
            ),
            models.UniqueConstraint(
                fields=["player", "pokemon_card"],
                name="unique_island_formation_pokemon",
            ),
            models.CheckConstraint(
                condition=Q(slot__gte=0, slot__lt=4),
                name="island_formation_slot_range",
            ),
            models.CheckConstraint(
                condition=Q(size__in=(2, 3, 4)),
                name="island_formation_size_allowed",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        start_row__isnull=True,
                        start_col__isnull=True,
                        orientation="",
                    )
                    | Q(
                        start_row__gte=0,
                        start_row__lt=8,
                        start_col__gte=0,
                        start_col__lt=8,
                        orientation__in=("H", "V"),
                    )
                ),
                name="island_formation_placement_shape",
            ),
        ]

    @property
    def is_placed(self):
        return self.start_row is not None

    @property
    def cells(self):
        if not self.is_placed:
            return []
        return [
            (
                self.start_row + (offset if self.orientation == self.Orientation.VERTICAL else 0),
                self.start_col + (offset if self.orientation == self.Orientation.HORIZONTAL else 0),
            )
            for offset in range(self.size)
        ]

    def __str__(self):
        return f"{self.pokemon_card.name_fr} ({self.size}) @ {self.player_id}"


class Shot(models.Model):
    class Result(models.TextChoices):
        MISS = "MISS", "Raté"
        HIT = "HIT", "Touché"
        CAPTURED = "CAPTURED", "Capturé"

    game = models.ForeignKey(
        IslandGame,
        on_delete=models.CASCADE,
        related_name="shots",
    )
    shooter = models.ForeignKey(
        IslandPlayer,
        on_delete=models.CASCADE,
        related_name="shots_fired",
    )
    target = models.ForeignKey(
        IslandPlayer,
        on_delete=models.CASCADE,
        related_name="shots_received",
    )
    row = models.PositiveSmallIntegerField()
    col = models.PositiveSmallIntegerField()
    result = models.CharField(max_length=10, choices=Result.choices)
    formation = models.ForeignKey(
        Formation,
        on_delete=models.SET_NULL,
        related_name="hits",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "target", "row", "col"],
                name="unique_island_shot_per_target_cell",
            ),
            models.CheckConstraint(
                condition=Q(row__gte=0, row__lt=8, col__gte=0, col__lt=8),
                name="island_shot_coordinate_range",
            ),
            models.CheckConstraint(
                condition=~Q(shooter=F("target")),
                name="island_shot_distinct_players",
            ),
            models.CheckConstraint(
                condition=(
                    Q(result="MISS", formation__isnull=True)
                    | Q(result__in=("HIT", "CAPTURED"), formation__isnull=False)
                ),
                name="island_shot_result_matches_formation",
            ),
        ]

    def __str__(self):
        return f"{self.shooter_id} → {chr(65 + self.col)}{self.row + 1}: {self.result}"


# API de domaine courte pour les appels externes (`islands.models.Game`) tout
# en conservant des noms de tables explicites dans l'admin et les migrations.
Game = IslandGame
Player = IslandPlayer
