import uuid

from django.conf import settings
from django.db import models


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

    pokedex_id = models.PositiveIntegerField(unique=True)
    slug = models.SlugField(unique=True)
    name_fr = models.CharField(max_length=50)
    name_en = models.CharField(max_length=50)

    primary_type = models.ForeignKey(
        PokemonType,
        on_delete=models.PROTECT,
        related_name="primary_cards",
    )

    secondary_type = models.ForeignKey(
        PokemonType,
        on_delete=models.PROTECT,
        related_name="secondary_cards",
        null=True,
        blank=True,
    )

    sprite_url = models.URLField()
    is_legendary = models.BooleanField(default=False)

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
        return [
            pokemon_type
            for pokemon_type in (
                self.primary_type,
                self.secondary_type,
            )
            if pokemon_type is not None
        ]


class Game(models.Model):
    """Une partie : son état, ses réglages et le curseur de tour."""

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.EN_ATTENTE,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_games",
    )

    max_players = models.PositiveSmallIntegerField(default=6)
    direction = models.SmallIntegerField(default=1)
    current_turn_number = models.PositiveSmallIntegerField(default=0)
    turn_revision = models.PositiveBigIntegerField(default=0)
    card_sequence_counter = models.PositiveIntegerField(default=0)

    selected_types = models.ManyToManyField(
        PokemonType,
        related_name="games",
        blank=True,
        help_text=("Les types tirés au sort au démarrage : " "la pioche n'en contient pas d'autres."),
    )

    active_type = models.ForeignKey(
        PokemonType,
        on_delete=models.PROTECT,
        related_name="active_games",
        null=True,
        blank=True,
        help_text="Type déclaré par le dernier joker joué.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Partie {self.id} " f"({self.get_status_display()})"

    def next_card_sequence(self):
        self.card_sequence_counter += 1
        return self.card_sequence_counter


class GamePlayer(models.Model):
    """Un joueur inscrit à une partie : son ordre de tour et son score."""

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="players",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_participations",
        null=True,
        blank=True,
    )

    bot_name = models.CharField(
        max_length=40,
        blank=True,
        default="",
    )

    turn_order = models.PositiveSmallIntegerField()
    score = models.PositiveIntegerField(default=0)
    has_called_uno = models.BooleanField(default=False)
    has_protection = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_order"]

        constraints = [
            models.UniqueConstraint(
                fields=["game", "user"],
                name="unique_player_per_game",
            ),
            models.UniqueConstraint(
                fields=["game", "turn_order"],
                name="unique_turn_order_per_game",
            ),
            models.UniqueConstraint(
                fields=["game", "bot_name"],
                condition=~models.Q(bot_name=""),
                name="unique_bot_name_per_game",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        user__isnull=True,
                    )
                    & ~models.Q(bot_name="")
                )
                | models.Q(
                    user__isnull=False,
                    bot_name="",
                ),
                name="valid_game_player_controller",
            ),
        ]

    def __str__(self):
        return f"{self.display_name} @ {self.game_id}"

    @property
    def display_name(self):
        if self.is_bot:
            return self.bot_name

        return self.user.get_username()

    @property
    def is_bot(self):
        return self.user_id is None


class GameCard(models.Model):
    """Une carte physique dans une partie précise."""

    class Location(models.TextChoices):
        PIOCHE = "PIOCHE", "Pioche"
        MAIN = "MAIN", "Main"
        DEFAUSSE = "DEFAUSSE", "Défausse"

    class Action(models.TextChoices):
        NORMAL = "NORMAL", "Aucun effet"
        DRAW_TWO = "DRAW_TWO", "+2"
        DRAW_FOUR = "DRAW_FOUR", "+4"
        REVERSE = "REVERSE", "Inversion"
        SHIELD = "SHIELD", "Protection"

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="cards",
    )

    pokemon_card = models.ForeignKey(
        PokemonCard,
        on_delete=models.PROTECT,
        related_name="instances",
    )

    location = models.CharField(
        max_length=10,
        choices=Location.choices,
        default=Location.PIOCHE,
    )

    action = models.CharField(
        max_length=10,
        choices=Action.choices,
        default=Action.NORMAL,
    )

    owner = models.ForeignKey(
        GamePlayer,
        on_delete=models.CASCADE,
        related_name="hand_cards",
        null=True,
        blank=True,
    )

    order_index = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "game",
                    "location",
                    "order_index",
                ]
            ),
        ]

    def __str__(self):
        return f"{self.pokemon_card.name_fr} " f"[{self.location}]"


class MoveLog(models.Model):
    """Historique traçable des événements d'une partie."""

    class MoveType(models.TextChoices):
        DEBUT_PARTIE = "DEBUT_PARTIE", "Début de partie"
        DISTRIBUTION = "DISTRIBUTION", "Distribution"
        JOUER_CARTE = "JOUER_CARTE", "Carte jouée"
        PIOCHER = "PIOCHER", "Pioche"
        MELANGE_DEFAUSSE = (
            "MELANGE_DEFAUSSE",
            "Mélange de la défausse",
        )
        FIN_PARTIE = "FIN_PARTIE", "Fin de partie"
        ABANDON = (
            "ABANDON",
            "Partie fermée pour inactivité",
        )

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="move_logs",
    )

    player = models.ForeignKey(
        GamePlayer,
        on_delete=models.SET_NULL,
        related_name="moves",
        null=True,
        blank=True,
    )

    move_type = models.CharField(
        max_length=20,
        choices=MoveType.choices,
    )

    game_card = models.ForeignKey(
        GameCard,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    declared_type = models.ForeignKey(
        PokemonType,
        on_delete=models.SET_NULL,
        related_name="declarations",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.move_type} — {self.game_id}"


class Profile(models.Model):
    """Profil public et statistiques d'un utilisateur."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    avatar = models.ImageField(
        upload_to="profiles/avatars/%Y/%m/",
        blank=True,
    )

    description = models.TextField(
        max_length=500,
        blank=True,
    )

    total_games_played = models.PositiveIntegerField(
        default=0,
    )

    total_games_won = models.PositiveIntegerField(
        default=0,
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profil de {self.user}"


class Friendship(models.Model):
    """Demande d'ami et relation entre deux utilisateurs."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        ACCEPTED = "ACCEPTED", "Acceptée"
        REJECTED = "REJECTED", "Refusée"

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_sent",
    )

    addressee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_received",
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    pair_key = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.CheckConstraint(
                condition=~models.Q(
                    requester=models.F("addressee"),
                ),
                name="friendship_users_must_be_different",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "requester",
                    "status",
                ]
            ),
            models.Index(
                fields=[
                    "addressee",
                    "status",
                ]
            ),
        ]

    def save(self, *args, **kwargs):
        if self.requester_id and self.addressee_id:
            first_id, second_id = sorted(
                (
                    self.requester_id,
                    self.addressee_id,
                )
            )

            self.pair_key = f"{first_id}:{second_id}"

        super().save(*args, **kwargs)

    def get_other_user(self, user):
        """Retourne l'autre utilisateur de la relation."""

        if user.pk == self.requester_id:
            return self.addressee

        if user.pk == self.addressee_id:
            return self.requester

        raise ValueError("Cet utilisateur ne fait pas partie " "de cette relation.")

    def __str__(self):
        return f"{self.requester} → " f"{self.addressee} " f"({self.get_status_display()})"


class GameInvitation(models.Model):
    """Invitation envoyée à un ami pour rejoindre un salon de jeu."""

    class Mode(models.TextChoices):
        POKE_UNO = "POKE_UNO", "Poké-Uno"
        GUESSWHO = "GUESSWHO", "Qui est-ce ?"
        SILHOUETTE = "SILHOUETTE", "Silhouette"
        PICTIONARY = "PICTIONARY", "Pictionary"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        ACCEPTED = "ACCEPTED", "Acceptée"
        DECLINED = "DECLINED", "Refusée"
        CANCELLED = "CANCELLED", "Annulée"
        EXPIRED = "EXPIRED", "Expirée"

    mode = models.CharField(
        max_length=12,
        choices=Mode.choices,
        default=Mode.POKE_UNO,
    )

    # Salon Poké-Uno
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="invitations",
        null=True,
        blank=True,
    )

    # Salon Qui est-ce ?
    guesswho_game = models.ForeignKey(
        "guesswho.GuessWhoGame",
        on_delete=models.CASCADE,
        related_name="invitations",
        null=True,
        blank=True,
    )

    # Salon Silhouette
    silhouette_game = models.ForeignKey(
        "silhouette.SilhouetteGame",
        on_delete=models.CASCADE,
        related_name="invitations",
        null=True,
        blank=True,
    )

    # Salon Pictionary
    pictionary_game = models.ForeignKey(
        "pictionary.PictionaryGame",
        on_delete=models.CASCADE,
        related_name="invitations",
        null=True,
        blank=True,
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_invitations_sent",
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_invitations_received",
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    responded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.CheckConstraint(
                condition=~models.Q(
                    sender=models.F("recipient"),
                ),
                name="game_invitation_users_must_be_different",
            ),
            # Une invitation doit pointer vers un seul type de salon.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        mode="POKE_UNO",
                        game__isnull=False,
                        guesswho_game__isnull=True,
                        silhouette_game__isnull=True,
                        pictionary_game__isnull=True,
                    )
                    | models.Q(
                        mode="GUESSWHO",
                        game__isnull=True,
                        guesswho_game__isnull=False,
                        silhouette_game__isnull=True,
                        pictionary_game__isnull=True,
                    )
                    | models.Q(
                        mode="SILHOUETTE",
                        game__isnull=True,
                        guesswho_game__isnull=True,
                        silhouette_game__isnull=False,
                        pictionary_game__isnull=True,
                    )
                    | models.Q(
                        mode="PICTIONARY",
                        game__isnull=True,
                        guesswho_game__isnull=True,
                        silhouette_game__isnull=True,
                        pictionary_game__isnull=False,
                    )
                ),
                name="game_invitation_has_one_valid_room",
            ),
            # Une seule invitation en attente par joueur et salon Poké-Uno.
            models.UniqueConstraint(
                fields=[
                    "game",
                    "recipient",
                ],
                condition=models.Q(
                    status="PENDING",
                    game__isnull=False,
                ),
                name="unique_pending_game_invitation",
            ),
            # Une seule invitation en attente par joueur et salon Qui est-ce.
            models.UniqueConstraint(
                fields=[
                    "guesswho_game",
                    "recipient",
                ],
                condition=models.Q(
                    status="PENDING",
                    guesswho_game__isnull=False,
                ),
                name="unique_pending_guesswho_invitation",
            ),
            # Une seule invitation en attente par joueur et salon Silhouette.
            models.UniqueConstraint(
                fields=[
                    "silhouette_game",
                    "recipient",
                ],
                condition=models.Q(
                    status="PENDING",
                    silhouette_game__isnull=False,
                ),
                name="unique_pending_silhouette_invitation",
            ),
            # Une seule invitation en attente par joueur et salon Pictionary.
            models.UniqueConstraint(
                fields=[
                    "pictionary_game",
                    "recipient",
                ],
                condition=models.Q(
                    status="PENDING",
                    pictionary_game__isnull=False,
                ),
                name="unique_pending_pictionary_invitation",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "recipient",
                    "status",
                ]
            ),
            models.Index(
                fields=[
                    "sender",
                    "status",
                ]
            ),
            models.Index(
                fields=[
                    "mode",
                    "status",
                ]
            ),
        ]

    @property
    def room(self):
        """Retourne le salon associé, quel que soit le jeu."""

        if self.mode == self.Mode.POKE_UNO:
            return self.game

        if self.mode == self.Mode.GUESSWHO:
            return self.guesswho_game

        if self.mode == self.Mode.SILHOUETTE:
            return self.silhouette_game

        if self.mode == self.Mode.PICTIONARY:
            return self.pictionary_game

        return None

    @property
    def room_id(self):
        room = self.room

        if room is None:
            return None

        return room.pk

    @property
    def mode_slug(self):
        slugs = {
            self.Mode.POKE_UNO: "poke-uno",
            self.Mode.GUESSWHO: "qui-est-ce",
            self.Mode.SILHOUETTE: "silhouette",
            self.Mode.PICTIONARY: "pictionary",
        }

        return slugs.get(self.mode, "")

    def __str__(self):
        return (
            f"{self.get_mode_display()} : "
            f"{self.sender} → {self.recipient} "
            f"({self.get_status_display()})"
        )
