import uuid

from django.conf import settings
from django.db import models


class GuessWhoGame(models.Model):
    """Partie de Qui est-ce ? limitée à deux joueurs humains."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        CHOIX = "CHOIX", "Choix secret"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EN_ATTENTE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guesswho_created_games",
    )
    current_turn = models.ForeignKey(
        "GuessWhoPlayer",
        on_delete=models.SET_NULL,
        related_name="current_turn_games",
        null=True,
        blank=True,
    )
    winner = models.ForeignKey(
        "GuessWhoPlayer",
        on_delete=models.SET_NULL,
        related_name="won_guesswho_games",
        null=True,
        blank=True,
    )
    turn_revision = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Qui est-ce ? {self.id} ({self.get_status_display()})"

    @property
    def max_players(self):
        return 2


class GuessWhoPlayer(models.Model):
    """Un des deux participants humains et son choix secret."""

    game = models.ForeignKey(GuessWhoGame, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guesswho_participations",
    )
    turn_order = models.PositiveSmallIntegerField()
    target_card = models.ForeignKey(
        "game.PokemonCard",
        on_delete=models.PROTECT,
        related_name="guesswho_targets",
        null=True,
        blank=True,
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "user"],
                name="unique_guesswho_user_per_game",
            ),
            models.UniqueConstraint(
                fields=["game", "turn_order"],
                name="unique_guesswho_turn_order",
            ),
            models.CheckConstraint(
                condition=models.Q(turn_order__in=(0, 1)),
                name="guesswho_turn_order_zero_or_one",
            ),
        ]

    def __str__(self):
        return f"{self.user.get_username()} @ {self.game_id}"


class GuessWhoRosterCard(models.Model):
    """Carte du plateau commun, figée à la création de la partie."""

    game = models.ForeignKey(GuessWhoGame, on_delete=models.CASCADE, related_name="roster_cards")
    pokemon_card = models.ForeignKey(
        "game.PokemonCard",
        on_delete=models.PROTECT,
        related_name="guesswho_roster_entries",
    )
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "pokemon_card"],
                name="unique_guesswho_roster_card",
            ),
            models.UniqueConstraint(
                fields=["game", "position"],
                name="unique_guesswho_roster_position",
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=0, position__lt=24),
                name="guesswho_roster_position_range",
            ),
        ]

    def __str__(self):
        return f"{self.position + 1}. {self.pokemon_card}"


class GuessWhoCandidateState(models.Model):
    """Note privée d'un joueur : carte abaissée ou encore candidate."""

    player = models.ForeignKey(
        GuessWhoPlayer,
        on_delete=models.CASCADE,
        related_name="candidate_states",
    )
    roster_card = models.ForeignKey(
        GuessWhoRosterCard,
        on_delete=models.CASCADE,
        related_name="player_states",
    )
    is_eliminated = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "roster_card"],
                name="unique_guesswho_candidate_state",
            )
        ]


class GuessWhoTurn(models.Model):
    """Historique ordonné des questions/réponses et des propositions."""

    class Kind(models.TextChoices):
        QUESTION = "QUESTION", "Question"
        GUESS = "GUESS", "Proposition"

    game = models.ForeignKey(GuessWhoGame, on_delete=models.CASCADE, related_name="turns")
    sequence = models.PositiveIntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    actor = models.ForeignKey(
        GuessWhoPlayer,
        on_delete=models.CASCADE,
        related_name="guesswho_turns",
    )
    question = models.CharField(max_length=500, blank=True, default="")
    answer = models.BooleanField(null=True, blank=True)
    responder = models.ForeignKey(
        GuessWhoPlayer,
        on_delete=models.SET_NULL,
        related_name="guesswho_responses",
        null=True,
        blank=True,
    )
    guessed_card = models.ForeignKey(
        "game.PokemonCard",
        on_delete=models.PROTECT,
        related_name="guesswho_guesses",
        null=True,
        blank=True,
    )
    is_correct = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "sequence"],
                name="unique_guesswho_turn_sequence",
            ),
            models.UniqueConstraint(
                fields=["game"],
                condition=models.Q(kind="QUESTION", answer__isnull=True),
                name="one_pending_guesswho_question",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="QUESTION",
                        guessed_card__isnull=True,
                        is_correct__isnull=True,
                    )
                    & ~models.Q(question="")
                )
                | models.Q(
                    kind="GUESS",
                    question="",
                    answer__isnull=True,
                    responder__isnull=True,
                    guessed_card__isnull=False,
                    is_correct__isnull=False,
                ),
                name="valid_guesswho_turn_payload",
            ),
        ]

    def __str__(self):
        return f"{self.sequence}. {self.get_kind_display()} @ {self.game_id}"
