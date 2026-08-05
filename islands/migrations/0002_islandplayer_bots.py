import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("islands", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="islandplayer",
            name="unique_island_user_per_game",
        ),
        migrations.AddField(
            model_name="islandplayer",
            name="bot_name",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AlterField(
            model_name="islandplayer",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="island_participations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="islandplayer",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("game", "user"),
                name="unique_island_user_per_game",
            ),
        ),
        migrations.AddConstraint(
            model_name="islandplayer",
            constraint=models.UniqueConstraint(
                condition=models.Q(("bot_name", ""), _negated=True),
                fields=("game", "bot_name"),
                name="unique_island_bot_name_per_game",
            ),
        ),
        migrations.AddConstraint(
            model_name="islandplayer",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("user__isnull", True), models.Q(("bot_name", ""), _negated=True)),
                    models.Q(("user__isnull", False), ("bot_name", "")),
                    _connector="OR",
                ),
                name="island_valid_player_controller",
            ),
        ),
    ]
