from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("game", "0003_pokemoncard_in_current_deck"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="active_family",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ecosystem", "Écosystème toxique"),
                    ("shadows", "Royaume des ombres"),
                    ("forge", "Forge tellurique"),
                    ("arcane", "Arcane"),
                    ("tides", "Marées gelées"),
                    ("skyfire", "Ciel ardent"),
                    ("instinct", "Instinct combatif"),
                    ("storm", "Tempête draconique"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="gameplayer",
            name="bot_name",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="game",
            name="turn_revision",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="movelog",
            name="declared_family",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ecosystem", "Écosystème toxique"),
                    ("shadows", "Royaume des ombres"),
                    ("forge", "Forge tellurique"),
                    ("arcane", "Arcane"),
                    ("tides", "Marées gelées"),
                    ("skyfire", "Ciel ardent"),
                    ("instinct", "Instinct combatif"),
                    ("storm", "Tempête draconique"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="gameplayer",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="game_participations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="gameplayer",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("bot_name", "")),
                fields=("game", "bot_name"),
                name="unique_bot_name_per_game",
            ),
        ),
        migrations.AddConstraint(
            model_name="gameplayer",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("user__isnull", True)) & ~models.Q(("bot_name", ""))
                )
                | models.Q(("bot_name", ""), ("user__isnull", False)),
                name="valid_game_player_controller",
            ),
        ),
    ]
