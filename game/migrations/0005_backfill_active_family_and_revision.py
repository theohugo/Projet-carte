from django.db import migrations


TYPE_TO_FAMILY = {
    "bug": "ecosystem",
    "grass": "ecosystem",
    "poison": "ecosystem",
    "ghost": "shadows",
    "dark": "shadows",
    "ground": "forge",
    "rock": "forge",
    "steel": "forge",
    "psychic": "arcane",
    "fairy": "arcane",
    "water": "tides",
    "ice": "tides",
    "fire": "skyfire",
    "flying": "skyfire",
    "normal": "instinct",
    "fighting": "instinct",
    "electric": "storm",
    "dragon": "storm",
}


def backfill_active_family_and_revision(apps, schema_editor):
    Game = apps.get_model("game", "Game")

    for game in Game.objects.select_related("active_type").all().iterator():
        fields_to_update = []
        if game.active_type_id and not game.active_family:
            game.active_family = TYPE_TO_FAMILY.get(game.active_type.slug, "")
            fields_to_update.append("active_family")
        if game.status == "EN_COURS" and game.turn_revision == 0:
            game.turn_revision = 1
            fields_to_update.append("turn_revision")
        if fields_to_update:
            game.save(update_fields=fields_to_update)


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0004_type_families_and_bot_players"),
    ]

    operations = [
        migrations.RunPython(backfill_active_family_and_revision, migrations.RunPython.noop),
    ]
