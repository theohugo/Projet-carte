import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RocketGame',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('EN_ATTENTE', 'En attente'), ('NUIT', 'Nuit'), ('DISCUSSION', 'Discussion'), ('VOTE', 'Vote'), ('TERMINEE', 'Terminée')], default='EN_ATTENTE', max_length=16)),
                ('max_players', models.PositiveSmallIntegerField(default=12)),
                ('round_number', models.PositiveSmallIntegerField(default=0)),
                ('turn_revision', models.PositiveBigIntegerField(default=0)),
                ('winner_side', models.CharField(blank=True, choices=[('ALLIES', 'Alliance des Dresseurs'), ('ROCKET', 'Team Rocket')], max_length=8)),
                ('last_event', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rocket_created_games', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RocketPlayer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('turn_order', models.PositiveSmallIntegerField()),
                ('role', models.CharField(blank=True, choices=[('ROCKET', 'Agent Rocket'), ('DETECTIVE', 'Détective Looker'), ('GUARDIAN', 'Leuphorie gardienne'), ('TRAINER', 'Dresseur')], max_length=12)),
                ('is_alive', models.BooleanField(default=True)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='players', to='rocket.rocketgame')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rocket_participations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['turn_order'],
            },
        ),
        migrations.CreateModel(
            name='RocketNightAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_number', models.PositiveSmallIntegerField()),
                ('kind', models.CharField(choices=[('KILL', 'Sabotage'), ('INSPECT', 'Enquête'), ('PROTECT', 'Protection')], max_length=8)),
                ('result_is_rocket', models.BooleanField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='night_actions', to='rocket.rocketgame')),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='night_actions', to='rocket.rocketplayer')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='targeted_night_actions', to='rocket.rocketplayer')),
            ],
            options={
                'ordering': ['round_number', 'created_at'],
            },
        ),
        migrations.CreateModel(
            name='RocketMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_number', models.PositiveSmallIntegerField()),
                ('sequence', models.PositiveIntegerField()),
                ('body', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='rocket.rocketgame')),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rocket_messages', to='rocket.rocketplayer')),
            ],
            options={
                'ordering': ['sequence'],
            },
        ),
        migrations.CreateModel(
            name='RocketVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_number', models.PositiveSmallIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to='rocket.rocketgame')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes_received', to='rocket.rocketplayer')),
                ('voter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes_cast', to='rocket.rocketplayer')),
            ],
            options={
                'ordering': ['round_number', 'created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='rocketplayer',
            constraint=models.UniqueConstraint(fields=('game', 'user'), name='unique_rocket_user_per_game'),
        ),
        migrations.AddConstraint(
            model_name='rocketplayer',
            constraint=models.UniqueConstraint(fields=('game', 'turn_order'), name='unique_rocket_turn_order'),
        ),
        migrations.AddConstraint(
            model_name='rocketnightaction',
            constraint=models.UniqueConstraint(fields=('game', 'actor', 'round_number', 'kind'), name='unique_rocket_night_action'),
        ),
        migrations.AddIndex(
            model_name='rocketmessage',
            index=models.Index(fields=['game', 'sequence'], name='rocket_rock_game_id_80939a_idx'),
        ),
        migrations.AddConstraint(
            model_name='rocketmessage',
            constraint=models.UniqueConstraint(fields=('game', 'sequence'), name='unique_rocket_message_sequence'),
        ),
        migrations.AddConstraint(
            model_name='rocketvote',
            constraint=models.UniqueConstraint(fields=('game', 'voter', 'round_number'), name='unique_rocket_day_vote'),
        ),
    ]
