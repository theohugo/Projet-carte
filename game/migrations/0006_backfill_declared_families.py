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


def backfill_declared_families(apps, schema_editor):
    MoveLog = apps.get_model("game", "MoveLog")

    moves = MoveLog.objects.filter(declared_family="", declared_type__isnull=False).select_related(
        "declared_type"
    )
    for move in moves.iterator():
        family_slug = TYPE_TO_FAMILY.get(move.declared_type.slug)
        if family_slug:
            move.declared_family = family_slug
            move.save(update_fields=["declared_family"])


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0005_backfill_active_family_and_revision"),
    ]

    operations = [
        migrations.RunPython(backfill_declared_families, migrations.RunPython.noop),
    ]
