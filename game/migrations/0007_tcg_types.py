from django.db import migrations, models


TCG_TYPE_CHOICES = [
    ("grass", "Plante"),
    ("fire", "Feu"),
    ("water", "Eau"),
    ("lightning", "Électrique"),
    ("psychic", "Psy"),
    ("fighting", "Combat"),
    ("darkness", "Obscurité"),
    ("metal", "Métal"),
    ("dragon", "Dragon"),
    ("colorless", "Incolore"),
]

SOURCE_TYPE_TO_TCG_TYPE = {
    "grass": "grass",
    "bug": "grass",
    "fire": "fire",
    "water": "water",
    "ice": "water",
    "electric": "lightning",
    "psychic": "psychic",
    "ghost": "psychic",
    "fairy": "psychic",
    "fighting": "fighting",
    "ground": "fighting",
    "rock": "fighting",
    "dark": "darkness",
    "poison": "darkness",
    "steel": "metal",
    "dragon": "dragon",
    "normal": "colorless",
    "flying": "colorless",
}

# Les anciennes familles étaient plus larges que les types JCC. Pour une
# partie déjà en cours, on conserve leur couleur d'accent historique afin de
# ne jamais laisser un choix invalide après le déploiement.
LEGACY_FAMILY_TO_TCG_TYPE = {
    "ecosystem": "grass",
    "shadows": "psychic",
    "forge": "metal",
    "arcane": "psychic",
    "tides": "water",
    "skyfire": "fire",
    "instinct": "fighting",
    "storm": "lightning",
}


def migrate_tcg_types(apps, schema_editor):
    Game = apps.get_model("game", "Game")
    MoveLog = apps.get_model("game", "MoveLog")
    PokemonCard = apps.get_model("game", "PokemonCard")

    for card in PokemonCard.objects.select_related("primary_type").all().iterator():
        card.tcg_type = SOURCE_TYPE_TO_TCG_TYPE.get(card.primary_type.slug, "colorless")
        card.save(update_fields=["tcg_type"])

    for game in Game.objects.select_related("active_type").all().iterator():
        if game.active_type_id:
            game.active_tcg_type = SOURCE_TYPE_TO_TCG_TYPE.get(game.active_type.slug, "")
        elif game.legacy_active_family:
            game.active_tcg_type = LEGACY_FAMILY_TO_TCG_TYPE.get(game.legacy_active_family, "")
        if game.active_tcg_type:
            game.save(update_fields=["active_tcg_type"])

    for move in MoveLog.objects.select_related("declared_type").all().iterator():
        if move.declared_type_id:
            move.declared_tcg_type = SOURCE_TYPE_TO_TCG_TYPE.get(move.declared_type.slug, "")
        elif move.legacy_declared_family:
            move.declared_tcg_type = LEGACY_FAMILY_TO_TCG_TYPE.get(
                move.legacy_declared_family,
                "",
            )
        if move.declared_tcg_type:
            move.save(update_fields=["declared_tcg_type"])


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0006_backfill_declared_families"),
    ]

    operations = [
        migrations.RenameField(
            model_name="game",
            old_name="active_family",
            new_name="legacy_active_family",
        ),
        migrations.RenameField(
            model_name="movelog",
            old_name="declared_family",
            new_name="legacy_declared_family",
        ),
        migrations.AlterField(
            model_name="game",
            name="legacy_active_family",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AlterField(
            model_name="movelog",
            name="legacy_declared_family",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="pokemoncard",
            name="tcg_type",
            field=models.CharField(
                choices=TCG_TYPE_CHOICES,
                default="colorless",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="game",
            name="active_tcg_type",
            field=models.CharField(
                blank=True,
                choices=TCG_TYPE_CHOICES,
                default="",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="movelog",
            name="declared_tcg_type",
            field=models.CharField(
                blank=True,
                choices=TCG_TYPE_CHOICES,
                default="",
                max_length=12,
            ),
        ),
        migrations.RunPython(migrate_tcg_types, migrations.RunPython.noop),
    ]
