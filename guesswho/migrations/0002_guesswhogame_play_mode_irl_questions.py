from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("guesswho", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="guesswhogame",
            name="play_mode",
            field=models.CharField(
                choices=[("ONLINE", "En ligne"), ("IRL", "IRL")],
                default="ONLINE",
                max_length=8,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="guesswhoturn",
            name="valid_guesswho_turn_payload",
        ),
        migrations.AddConstraint(
            model_name="guesswhoturn",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("guessed_card__isnull", True),
                    ("is_correct__isnull", True),
                    ("kind", "QUESTION"),
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
        ),
    ]
