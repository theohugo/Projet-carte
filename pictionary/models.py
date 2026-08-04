import uuid

from django.conf import settings
from django.db import models


class PictionaryGame(models.Model):
    """Partie de Pictionary : un joueur dessine, les autres écrivent leurs réponses."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"

    class RoundCount(models.IntegerChoices):
        COURTE = 3, "3 manches"
        NORMALE = 6, "6 manches"
        LONGUE = 9, "9 manches"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EN_ATTENTE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pictionary_created_games",
    )
    round_count = models.PositiveSmallIntegerField(
        choices=RoundCount.choices,
        default=RoundCount.NORMALE,
        help_text="Nombre de manches, donc de dessinateurs successifs.",
    )
    turn_revision = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pictionary {self.id} ({self.get_status_display()})"


class PictionaryPlayer(models.Model):
    """Un participant, son ordre de passage au dessin et son score."""

    game = models.ForeignKey(PictionaryGame, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pictionary_participations",
    )
    turn_order = models.PositiveSmallIntegerField()
    score = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_order"]
        constraints = [
            models.UniqueConstraint(fields=["game", "user"], name="unique_pictionary_user_per_game"),
            models.UniqueConstraint(fields=["game", "turn_order"], name="unique_pictionary_turn_order"),
        ]

    def __str__(self):
        return f"{self.user.get_username()} @ {self.game_id}"


class PictionaryRound(models.Model):
    """Une manche : un dessinateur, une espèce à faire deviner, un chrono."""

    game = models.ForeignKey(PictionaryGame, on_delete=models.CASCADE, related_name="rounds")
    number = models.PositiveSmallIntegerField()
    drawer = models.ForeignKey(PictionaryPlayer, on_delete=models.CASCADE, related_name="drawn_rounds")
    pokemon_card = models.ForeignKey(
        "game.PokemonCard",
        on_delete=models.PROTECT,
        related_name="pictionary_rounds",
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["game", "number"], name="unique_pictionary_round_number"),
        ]

    def __str__(self):
        return f"Manche {self.number} — {self.game_id}"


class PictionaryStroke(models.Model):
    """Un trait du dessinateur, transmis aux autres par polling incrémental.

    Les points sont stockés tels quels : un trait est une donnée d'affichage
    éphémère, pas un état de jeu à requêter, et le curseur ``sequence`` suffit
    à n'envoyer que la nouveauté à chaque tour de polling.
    """

    round = models.ForeignKey(PictionaryRound, on_delete=models.CASCADE, related_name="strokes")
    sequence = models.PositiveIntegerField()
    points = models.JSONField(default=list)
    color = models.CharField(max_length=7, default="#f6f9ff")
    width = models.PositiveSmallIntegerField(default=4)
    is_clear = models.BooleanField(default=False, help_text="Efface tout ce qui précède.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["round", "sequence"], name="unique_stroke_sequence_per_round"),
        ]
        indexes = [models.Index(fields=["round", "sequence"])]

    def __str__(self):
        return f"Trait {self.sequence} — manche {self.round_id}"


class PictionaryGuess(models.Model):
    """Une proposition écrite par un joueur qui ne dessine pas."""

    round = models.ForeignKey(PictionaryRound, on_delete=models.CASCADE, related_name="guesses")
    player = models.ForeignKey(PictionaryPlayer, on_delete=models.CASCADE, related_name="guesses")
    text = models.CharField(max_length=60)
    is_correct = models.BooleanField(default=False)
    elapsed_ms = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["round", "player"],
                condition=models.Q(is_correct=True),
                name="unique_correct_pictionary_guess",
            ),
        ]

    def __str__(self):
        return f"{self.player_id}: {self.text}"
