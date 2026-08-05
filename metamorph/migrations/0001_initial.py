# Generated for the Metamorph Mystère application.
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("game", "0017_card_prints_and_rarities"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MetamorphGame",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("EN_ATTENTE", "En attente"),
                            ("EN_COURS", "En cours"),
                            ("TERMINEE", "Terminée"),
                        ],
                        default="EN_ATTENTE",
                        max_length=16,
                    ),
                ),
                ("direction", models.SmallIntegerField(default=1)),
                ("turn_revision", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metamorph_created_games",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("direction__in", (-1, 1))),
                        name="metamorph_direction_is_valid",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="MetamorphPlayer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("turn_order", models.PositiveSmallIntegerField()),
                ("rank", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("is_loser", models.BooleanField(default=False)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="players",
                        to="metamorph.metamorphgame",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metamorph_participations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["turn_order"],
                "constraints": [
                    models.UniqueConstraint(fields=("game", "user"), name="unique_metamorph_user_per_game"),
                    models.UniqueConstraint(fields=("game", "turn_order"), name="unique_metamorph_turn_order"),
                    models.UniqueConstraint(fields=("game", "rank"), name="unique_metamorph_rank"),
                    models.CheckConstraint(
                        condition=models.Q(("turn_order__gte", 0), ("turn_order__lt", 6)),
                        name="metamorph_turn_order_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("rank__isnull", True),
                            models.Q(("rank__gte", 1), ("rank__lte", 6)),
                            _connector="OR",
                        ),
                        name="metamorph_rank_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("is_loser", False), ("rank__isnull", False), _connector="OR"),
                        name="metamorph_loser_has_rank",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="metamorphgame",
            name="current_turn",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="current_turn_games",
                to="metamorph.metamorphplayer",
            ),
        ),
        migrations.CreateModel(
            name="MetamorphCard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("copy_index", models.PositiveSmallIntegerField(default=0)),
                ("is_ditto", models.BooleanField(default=False)),
                ("hand_position", models.PositiveSmallIntegerField(default=1)),
                ("paired_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cards",
                        to="metamorph.metamorphgame",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hand_cards",
                        to="metamorph.metamorphplayer",
                    ),
                ),
                (
                    "pokemon_card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="metamorph_cards",
                        to="game.pokemoncard",
                    ),
                ),
            ],
            options={
                "ordering": ["hand_position", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("game", "pokemon_card", "copy_index"),
                        name="unique_metamorph_physical_card",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("copy_index__in", (0, 1))),
                        name="metamorph_copy_index_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("is_ditto", False), ("copy_index", 0), _connector="OR"),
                        name="metamorph_ditto_has_single_copy",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("hand_position__gte", 1), ("owner__isnull", False), ("paired_at__isnull", True)),
                            models.Q(("hand_position", 0), ("owner__isnull", True), ("paired_at__isnull", False)),
                            _connector="OR",
                        ),
                        name="metamorph_card_lifecycle_is_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("is_ditto", False), ("paired_at__isnull", True), _connector="OR"),
                        name="metamorph_ditto_is_never_paired",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="MetamorphMove",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField()),
                ("formed_pair", models.BooleanField(default=False)),
                ("resulting_revision", models.PositiveBigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metamorph_moves",
                        to="metamorph.metamorphplayer",
                    ),
                ),
                (
                    "drawn_card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="draw_moves",
                        to="metamorph.metamorphcard",
                    ),
                ),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="moves",
                        to="metamorph.metamorphgame",
                    ),
                ),
                (
                    "paired_card",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pair_moves",
                        to="metamorph.metamorphcard",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metamorph_cards_given",
                        to="metamorph.metamorphplayer",
                    ),
                ),
            ],
            options={
                "ordering": ["sequence"],
                "constraints": [
                    models.UniqueConstraint(fields=("game", "sequence"), name="unique_metamorph_move_sequence"),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("formed_pair", True), ("paired_card__isnull", False)),
                            models.Q(("formed_pair", False), ("paired_card__isnull", True)),
                            _connector="OR",
                        ),
                        name="metamorph_move_pair_payload_is_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("actor", models.F("source")), _negated=True),
                        name="metamorph_move_uses_another_hand",
                    ),
                ],
            },
        ),
    ]
