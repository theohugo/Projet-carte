import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("starterrace", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="player",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="starterrace_participations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="player",
            name="bot_name",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddConstraint(
            model_name="player",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("bot_name", "")),
                fields=("game", "bot_name"),
                name="unique_starterrace_bot_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="player",
            constraint=models.CheckConstraint(
                condition=models.Q(("bot_name", ""), ("user__isnull", False))
                | (models.Q(("user__isnull", True)) & ~models.Q(("bot_name", ""))),
                name="starterrace_player_has_one_controller",
            ),
        ),
    ]
