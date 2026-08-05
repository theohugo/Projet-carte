from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rocket', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='rocketgame',
            name='phase_deadline',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
