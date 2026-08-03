from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0007_tcg_types"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="game",
            name="active_type",
        ),
        migrations.RemoveField(
            model_name="game",
            name="legacy_active_family",
        ),
        migrations.RemoveField(
            model_name="movelog",
            name="declared_type",
        ),
        migrations.RemoveField(
            model_name="movelog",
            name="legacy_declared_family",
        ),
    ]
