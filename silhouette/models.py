import uuid

from django.conf import settings
from django.db import models

from game.pokemon_names import localized_bot_name


class SilhouetteGame(models.Model):
    """Partie de « Qui est ce Pokémon ? », ouverte à autant de joueurs qu'on veut."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"

    class RoundCount(models.IntegerChoices):
        COURTE = 5, "5 manches"
        NORMALE = 10, "10 manches"
        LONGUE = 15, "15 manches"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EN_ATTENTE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="silhouette_created_games",
    )
    round_count = models.PositiveSmallIntegerField(
        choices=RoundCount.choices,
        default=RoundCount.NORMALE,
        help_text="Nombre de manches choisi par l'hôte à la création du salon.",
    )
    turn_revision = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Qui est ce Pokémon ? {self.id} ({self.get_status_display()})"


class SilhouettePlayer(models.Model):
    """Un participant et son score cumulé sur la partie."""

    game = models.ForeignKey(SilhouetteGame, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="silhouette_participations",
        null=True,
        blank=True,
    )
    bot_name = models.CharField(max_length=30, blank=True)
    score = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "joined_at"]
        constraints = [
            models.UniqueConstraint(fields=["game", "user"], name="unique_silhouette_user_per_game"),
        ]

    def __str__(self):
        return f"{self.display_name} @ {self.game_id}"

    @property
    def is_bot(self):
        return self.user_id is None

    @property
    def display_name(self):
        return localized_bot_name(self.bot_name) if self.is_bot else self.user.get_username()


class SilhouetteRound(models.Model):
    """Une manche : une espèce à reconnaître, et l'horloge qui pilote les indices."""

    game = models.ForeignKey(SilhouetteGame, on_delete=models.CASCADE, related_name="rounds")
    number = models.PositiveSmallIntegerField()
    pokemon_card = models.ForeignKey(
        "game.PokemonCard",
        on_delete=models.PROTECT,
        related_name="silhouette_rounds",
    )
    started_at = models.DateTimeField()
    revealed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["game", "number"], name="unique_silhouette_round_number"),
        ]

    def __str__(self):
        return f"Manche {self.number} — {self.game_id}"


class SilhouetteGuess(models.Model):
    """Une proposition. Les bonnes réponses portent le score gagné."""

    round = models.ForeignKey(SilhouetteRound, on_delete=models.CASCADE, related_name="guesses")
    player = models.ForeignKey(SilhouettePlayer, on_delete=models.CASCADE, related_name="guesses")
    text = models.CharField(max_length=60)
    is_correct = models.BooleanField(default=False)
    elapsed_ms = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            # Une seule bonne réponse par joueur et par manche : le score d'une
            # manche ne peut pas être encaissé deux fois.
            models.UniqueConstraint(
                fields=["round", "player"],
                condition=models.Q(is_correct=True),
                name="unique_correct_guess_per_round",
            ),
        ]

    def __str__(self):
        return f"{self.player_id}: {self.text}"
