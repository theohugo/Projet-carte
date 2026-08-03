import uuid

from django.conf import settings
from django.db import models

from game.tcg_types import TCG_TYPE_CHOICES


class PokemonType(models.Model):
    """Un des 18 types des jeux vidéo, conservé comme donnée source."""

    slug = models.SlugField(unique=True)
    name_fr = models.CharField(max_length=30)
    name_en = models.CharField(max_length=30)

    class Meta:
        ordering = ["name_en"]

    def __str__(self):
        return self.name_fr


class PokemonCard(models.Model):
    """Carte maîtresse du catalogue, partagée entre toutes les parties."""

    class Action(models.TextChoices):
        NORMAL = "NORMAL", "Aucun effet"
        DRAW_TWO = "DRAW_TWO", "+2"
        DRAW_FOUR = "DRAW_FOUR", "+4"
        REVERSE = "REVERSE", "Inversion"
        SHIELD = "SHIELD", "Protection"

    pokedex_id = models.PositiveIntegerField(unique=True)
    slug = models.SlugField(unique=True)
    name_fr = models.CharField(max_length=50)
    name_en = models.CharField(max_length=50)
    primary_type = models.ForeignKey(PokemonType, on_delete=models.PROTECT, related_name="primary_cards")
    secondary_type = models.ForeignKey(
        PokemonType,
        on_delete=models.PROTECT,
        related_name="secondary_cards",
        null=True,
        blank=True,
    )
    sprite_url = models.URLField()
    is_legendary = models.BooleanField(default=False)
    action = models.CharField(max_length=10, choices=Action.choices, default=Action.NORMAL)
    tcg_type = models.CharField(max_length=12, choices=TCG_TYPE_CHOICES, default="grass")
    in_current_deck = models.BooleanField(
        default=True,
        help_text="Inclure cette espèce dans les nouvelles parties.",
    )

    class Meta:
        ordering = ["pokedex_id"]

    def __str__(self):
        return f"#{self.pokedex_id} {self.name_fr}"

    @property
    def types(self):
        return [t for t in (self.primary_type, self.secondary_type) if t is not None]


class Game(models.Model):
    """Une partie : son état, ses réglages, et le curseur de tour."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EN_ATTENTE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_games"
    )
    max_players = models.PositiveSmallIntegerField(default=6)
    direction = models.SmallIntegerField(default=1)
    current_turn_number = models.PositiveSmallIntegerField(default=0)
    turn_revision = models.PositiveBigIntegerField(default=0)
    card_sequence_counter = models.PositiveIntegerField(default=0)
    active_tcg_type = models.CharField(
        max_length=12,
        choices=TCG_TYPE_CHOICES,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Partie {self.id} ({self.get_status_display()})"

    def next_card_sequence(self):
        self.card_sequence_counter += 1
        return self.card_sequence_counter


class GamePlayer(models.Model):
    """Un joueur inscrit à une partie : son ordre de tour et son score."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_participations",
        null=True,
        blank=True,
    )
    bot_name = models.CharField(max_length=40, blank=True, default="")
    turn_order = models.PositiveSmallIntegerField()
    score = models.PositiveIntegerField(default=0)
    has_called_uno = models.BooleanField(default=False)
    has_protection = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_order"]
        constraints = [
            models.UniqueConstraint(fields=["game", "user"], name="unique_player_per_game"),
            models.UniqueConstraint(fields=["game", "turn_order"], name="unique_turn_order_per_game"),
            models.UniqueConstraint(
                fields=["game", "bot_name"],
                condition=~models.Q(bot_name=""),
                name="unique_bot_name_per_game",
            ),
            models.CheckConstraint(
                condition=(models.Q(user__isnull=True) & ~models.Q(bot_name=""))
                | models.Q(user__isnull=False, bot_name=""),
                name="valid_game_player_controller",
            ),
        ]

    def __str__(self):
        return f"{self.display_name} @ {self.game_id}"

    @property
    def display_name(self):
        return self.bot_name if self.is_bot else self.user.get_username()

    @property
    def is_bot(self):
        return self.user_id is None


class GameCard(models.Model):
    """Une carte physique dans une partie précise : pioche, main d'un joueur, ou défausse."""

    class Location(models.TextChoices):
        PIOCHE = "PIOCHE", "Pioche"
        MAIN = "MAIN", "Main"
        DEFAUSSE = "DEFAUSSE", "Défausse"

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="cards")
    pokemon_card = models.ForeignKey(PokemonCard, on_delete=models.PROTECT, related_name="instances")
    location = models.CharField(max_length=10, choices=Location.choices, default=Location.PIOCHE)
    owner = models.ForeignKey(
        GamePlayer, on_delete=models.CASCADE, related_name="hand_cards", null=True, blank=True
    )
    order_index = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["game", "location", "order_index"])]

    def __str__(self):
        return f"{self.pokemon_card.name_fr} [{self.location}]"


class MoveLog(models.Model):
    """Historique traçable des événements d'une partie."""

    class MoveType(models.TextChoices):
        DEBUT_PARTIE = "DEBUT_PARTIE", "Début de partie"
        DISTRIBUTION = "DISTRIBUTION", "Distribution"
        JOUER_CARTE = "JOUER_CARTE", "Carte jouée"
        PIOCHER = "PIOCHER", "Pioche"
        MELANGE_DEFAUSSE = "MELANGE_DEFAUSSE", "Mélange de la défausse"
        FIN_PARTIE = "FIN_PARTIE", "Fin de partie"
        ABANDON = "ABANDON", "Partie fermée pour inactivité"

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="move_logs")
    player = models.ForeignKey(
        GamePlayer, on_delete=models.SET_NULL, related_name="moves", null=True, blank=True
    )
    move_type = models.CharField(max_length=20, choices=MoveType.choices)
    game_card = models.ForeignKey(GameCard, on_delete=models.SET_NULL, null=True, blank=True)
    declared_tcg_type = models.CharField(
        max_length=12,
        choices=TCG_TYPE_CHOICES,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.move_type} — {self.game_id}"


class Profile(models.Model):
    """Statistiques d'un utilisateur, indépendantes d'une partie précise."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    total_games_played = models.PositiveIntegerField(default=0)
    total_games_won = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Profil de {self.user}"
