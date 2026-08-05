import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("silhouette", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="silhouetteplayer",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="silhouette_participations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="silhouetteplayer",
            name="bot_name",
            field=models.CharField(blank=True, max_length=30),
        ),
    ]
