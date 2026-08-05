import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class MetamorphGame(models.Model):
    """Une table de Métamorph Mystère et son curseur de tour."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EN_ATTENTE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="metamorph_created_games",
    )
    current_turn = models.ForeignKey(
        "MetamorphPlayer",
        on_delete=models.SET_NULL,
        related_name="current_turn_games",
        null=True,
        blank=True,
    )
    direction = models.SmallIntegerField(default=1)
    turn_revision = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(direction__in=(-1, 1)),
                name="metamorph_direction_is_valid",
            ),
        ]

    @property
    def min_players(self):
        return 2

    @property
    def max_players(self):
        return 6

    def __str__(self):
        return f"Métamorph Mystère {self.id} ({self.get_status_display()})"


class MetamorphPlayer(models.Model):
    """Un participant, son siège et son classement final."""

    game = models.ForeignKey(MetamorphGame, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="metamorph_participations",
    )
    turn_order = models.PositiveSmallIntegerField()
    rank = models.PositiveSmallIntegerField(null=True, blank=True)
    is_loser = models.BooleanField(default=False)
    finished_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "user"],
                name="unique_metamorph_user_per_game",
            ),
            models.UniqueConstraint(
                fields=["game", "turn_order"],
                name="unique_metamorph_turn_order",
            ),
            models.UniqueConstraint(
                fields=["game", "rank"],
                name="unique_metamorph_rank",
            ),
            models.CheckConstraint(
                condition=Q(turn_order__gte=0, turn_order__lt=6),
                name="metamorph_turn_order_range",
            ),
            models.CheckConstraint(
                condition=Q(rank__isnull=True) | Q(rank__gte=1, rank__lte=6),
                name="metamorph_rank_range",
            ),
            models.CheckConstraint(
                condition=Q(is_loser=False) | Q(rank__isnull=False),
                name="metamorph_loser_has_rank",
            ),
        ]

    def __str__(self):
        return f"{self.user.get_username()} @ {self.game_id}"


class MetamorphCard(models.Model):
    """Une carte physique : deux copies par paire, une seule pour Métamorph."""

    game = models.ForeignKey(MetamorphGame, on_delete=models.CASCADE, related_name="cards")
    pokemon_card = models.ForeignKey(
        "game.PokemonCard",
        on_delete=models.PROTECT,
        related_name="metamorph_cards",
    )
    owner = models.ForeignKey(
        MetamorphPlayer,
        on_delete=models.CASCADE,
        related_name="hand_cards",
        null=True,
        blank=True,
    )
    copy_index = models.PositiveSmallIntegerField(default=0)
    is_ditto = models.BooleanField(default=False)
    hand_position = models.PositiveSmallIntegerField(default=1)
    paired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["hand_position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "pokemon_card", "copy_index"],
                name="unique_metamorph_physical_card",
            ),
            models.CheckConstraint(
                condition=Q(copy_index__in=(0, 1)),
                name="metamorph_copy_index_range",
            ),
            models.CheckConstraint(
                condition=Q(is_ditto=False) | Q(copy_index=0),
                name="metamorph_ditto_has_single_copy",
            ),
            models.CheckConstraint(
                condition=(
                    Q(owner__isnull=False, paired_at__isnull=True, hand_position__gte=1)
                    | Q(owner__isnull=True, paired_at__isnull=False, hand_position=0)
                ),
                name="metamorph_card_lifecycle_is_valid",
            ),
            models.CheckConstraint(
                condition=Q(is_ditto=False) | Q(paired_at__isnull=True),
                name="metamorph_ditto_is_never_paired",
            ),
        ]

    def __str__(self):
        suffix = "Métamorph" if self.is_ditto else f"copie {self.copy_index + 1}"
        return f"{self.pokemon_card.name_fr} — {suffix}"


class MetamorphMove(models.Model):
    """Un tirage ordonné ; la carte exacte reste confidentielle côté API."""

    game = models.ForeignKey(MetamorphGame, on_delete=models.CASCADE, related_name="moves")
    sequence = models.PositiveIntegerField()
    actor = models.ForeignKey(
        MetamorphPlayer,
        on_delete=models.CASCADE,
        related_name="metamorph_moves",
    )
    source = models.ForeignKey(
        MetamorphPlayer,
        on_delete=models.CASCADE,
        related_name="metamorph_cards_given",
    )
    drawn_card = models.ForeignKey(
        MetamorphCard,
        on_delete=models.CASCADE,
        related_name="draw_moves",
    )
    paired_card = models.ForeignKey(
        MetamorphCard,
        on_delete=models.SET_NULL,
        related_name="pair_moves",
        null=True,
        blank=True,
    )
    formed_pair = models.BooleanField(default=False)
    resulting_revision = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "sequence"],
                name="unique_metamorph_move_sequence",
            ),
            models.CheckConstraint(
                condition=(
                    Q(formed_pair=True, paired_card__isnull=False)
                    | Q(formed_pair=False, paired_card__isnull=True)
                ),
                name="metamorph_move_pair_payload_is_valid",
            ),
            models.CheckConstraint(
                condition=~Q(actor=F("source")),
                name="metamorph_move_uses_another_hand",
            ),
        ]

    def __str__(self):
        return f"Coup {self.sequence} @ {self.game_id}"
