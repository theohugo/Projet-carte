from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("game", "0002_card_actions_and_player_protection")]

    operations = [
        migrations.AddField(
            model_name="pokemoncard",
            name="in_current_deck",
            field=models.BooleanField(
                default=True,
                help_text="Inclure cette espèce dans les nouvelles parties.",
            ),
        ),
    ]
