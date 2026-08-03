# Generated manually for the autonomous guesswho application.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("game", "0007_tcg_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="GuessWhoGame",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("EN_ATTENTE", "En attente"),
                            ("CHOIX", "Choix secret"),
                            ("EN_COURS", "En cours"),
                            ("TERMINEE", "Terminée"),
                        ],
                        default="EN_ATTENTE",
                        max_length=16,
                    ),
                ),
                ("turn_revision", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guesswho_created_games",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GuessWhoPlayer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("turn_order", models.PositiveSmallIntegerField()),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="players",
                        to="guesswho.guesswhogame",
                    ),
                ),
                (
                    "target_card",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guesswho_targets",
                        to="game.pokemoncard",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guesswho_participations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["turn_order"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("game", "user"),
                        name="unique_guesswho_user_per_game",
                    ),
                    models.UniqueConstraint(
                        fields=("game", "turn_order"),
                        name="unique_guesswho_turn_order",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("turn_order__in", (0, 1))),
                        name="guesswho_turn_order_zero_or_one",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="guesswhogame",
            name="current_turn",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="current_turn_games",
                to="guesswho.guesswhoplayer",
            ),
        ),
        migrations.AddField(
            model_name="guesswhogame",
            name="winner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="won_guesswho_games",
                to="guesswho.guesswhoplayer",
            ),
        ),
        migrations.CreateModel(
            name="GuessWhoRosterCard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField()),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="roster_cards",
                        to="guesswho.guesswhogame",
                    ),
                ),
                (
                    "pokemon_card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guesswho_roster_entries",
                        to="game.pokemoncard",
                    ),
                ),
            ],
            options={
                "ordering": ["position"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("game", "pokemon_card"),
                        name="unique_guesswho_roster_card",
                    ),
                    models.UniqueConstraint(
                        fields=("game", "position"),
                        name="unique_guesswho_roster_position",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("position__gte", 0), ("position__lt", 24)),
                        name="guesswho_roster_position_range",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="GuessWhoCandidateState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_eliminated", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="candidate_states",
                        to="guesswho.guesswhoplayer",
                    ),
                ),
                (
                    "roster_card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="player_states",
                        to="guesswho.guesswhorostercard",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("player", "roster_card"),
                        name="unique_guesswho_candidate_state",
                    )
                ]
            },
        ),
        migrations.CreateModel(
            name="GuessWhoTurn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField()),
                (
                    "kind",
                    models.CharField(
                        choices=[("QUESTION", "Question"), ("GUESS", "Proposition")],
                        max_length=10,
                    ),
                ),
                ("question", models.CharField(blank=True, default="", max_length=500)),
                ("answer", models.BooleanField(blank=True, null=True)),
                ("is_correct", models.BooleanField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("answered_at", models.DateTimeField(blank=True, null=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guesswho_turns",
                        to="guesswho.guesswhoplayer",
                    ),
                ),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="turns",
                        to="guesswho.guesswhogame",
                    ),
                ),
                (
                    "guessed_card",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guesswho_guesses",
                        to="game.pokemoncard",
                    ),
                ),
                (
                    "responder",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="guesswho_responses",
                        to="guesswho.guesswhoplayer",
                    ),
                ),
            ],
            options={
                "ordering": ["sequence"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("game", "sequence"),
                        name="unique_guesswho_turn_sequence",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("answer__isnull", True), ("kind", "QUESTION")),
                        fields=("game",),
                        name="one_pending_guesswho_question",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("guessed_card__isnull", True),
                                ("is_correct__isnull", True),
                                ("kind", "QUESTION"),
                            )
                            & ~models.Q(("question", ""))
                        )
                        | models.Q(
                            ("answer__isnull", True),
                            ("guessed_card__isnull", False),
                            ("is_correct__isnull", False),
                            ("kind", "GUESS"),
                            ("question", ""),
                            ("responder__isnull", True),
                        ),
                        name="valid_guesswho_turn_payload",
                    ),
                ],
            },
        ),
    ]
