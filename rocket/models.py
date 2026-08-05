import uuid

from django.conf import settings
from django.db import models


class RocketGame(models.Model):
    """Une partie sociale à rôles cachés, découpée en nuits, débats et votes."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        NUIT = "NUIT", "Nuit"
        DISCUSSION = "DISCUSSION", "Discussion"
        VOTE = "VOTE", "Vote"
        TERMINEE = "TERMINEE", "Terminée"

    class WinnerSide(models.TextChoices):
        ALLIES = "ALLIES", "Alliance des Dresseurs"
        ROCKET = "ROCKET", "Team Rocket"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EN_ATTENTE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rocket_created_games",
    )
    max_players = models.PositiveSmallIntegerField(default=12)
    round_number = models.PositiveSmallIntegerField(default=0)
    turn_revision = models.PositiveBigIntegerField(default=0)
    winner_side = models.CharField(max_length=8, choices=WinnerSide.choices, blank=True)
    last_event = models.JSONField(default=dict, blank=True)
    phase_deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Infiltration Rocket {self.id} ({self.get_status_display()})"


class RocketPlayer(models.Model):
    """Participant et rôle secret. Le rôle n'est jamais exposé par le modèle HTTP brut."""

    class Role(models.TextChoices):
        ROCKET = "ROCKET", "Agent Rocket"
        DETECTIVE = "DETECTIVE", "Détective Looker"
        GUARDIAN = "GUARDIAN", "Leuphorie gardienne"
        TRAINER = "TRAINER", "Dresseur"

    game = models.ForeignKey(RocketGame, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rocket_participations",
    )
    turn_order = models.PositiveSmallIntegerField()
    role = models.CharField(max_length=12, choices=Role.choices, blank=True)
    is_alive = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_order"]
        constraints = [
            models.UniqueConstraint(fields=["game", "user"], name="unique_rocket_user_per_game"),
            models.UniqueConstraint(fields=["game", "turn_order"], name="unique_rocket_turn_order"),
        ]

    def __str__(self):
        return f"{self.user.get_username()} @ {self.game_id}"


class RocketNightAction(models.Model):
    """Choix privé d'un rôle pendant une nuit."""

    class Kind(models.TextChoices):
        KILL = "KILL", "Sabotage"
        INSPECT = "INSPECT", "Enquête"
        PROTECT = "PROTECT", "Protection"

    game = models.ForeignKey(RocketGame, on_delete=models.CASCADE, related_name="night_actions")
    actor = models.ForeignKey(RocketPlayer, on_delete=models.CASCADE, related_name="night_actions")
    target = models.ForeignKey(RocketPlayer, on_delete=models.CASCADE, related_name="targeted_night_actions")
    round_number = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=8, choices=Kind.choices)
    result_is_rocket = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["round_number", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "actor", "round_number", "kind"],
                name="unique_rocket_night_action",
            )
        ]


class RocketVote(models.Model):
    """Bulletin privé du conseil de jour."""

    game = models.ForeignKey(RocketGame, on_delete=models.CASCADE, related_name="votes")
    voter = models.ForeignKey(RocketPlayer, on_delete=models.CASCADE, related_name="votes_cast")
    target = models.ForeignKey(RocketPlayer, on_delete=models.CASCADE, related_name="votes_received")
    round_number = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["round_number", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "voter", "round_number"],
                name="unique_rocket_day_vote",
            )
        ]


class RocketMessage(models.Model):
    """Message du débat, ordonné par un curseur monotone pour le polling."""

    game = models.ForeignKey(RocketGame, on_delete=models.CASCADE, related_name="messages")
    player = models.ForeignKey(RocketPlayer, on_delete=models.CASCADE, related_name="rocket_messages")
    round_number = models.PositiveSmallIntegerField()
    sequence = models.PositiveIntegerField()
    body = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["game", "sequence"], name="unique_rocket_message_sequence")
        ]
        indexes = [models.Index(fields=["game", "sequence"])]
