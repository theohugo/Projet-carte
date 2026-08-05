import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('game', '0017_card_prints_and_rarities'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IslandGame',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('EN_ATTENTE', 'En attente'), ('PLACEMENT', 'Placement'), ('EN_COURS', 'En cours'), ('TERMINEE', 'Terminée')], default='EN_ATTENTE', max_length=16)),
                ('turn_revision', models.PositiveBigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='island_created_games', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='IslandPlayer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('turn_order', models.PositiveSmallIntegerField()),
                ('is_ready', models.BooleanField(default=False)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='players', to='islands.islandgame')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='island_participations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['turn_order'],
            },
        ),
        migrations.AddField(
            model_name='islandgame',
            name='current_turn',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='current_turn_games', to='islands.islandplayer'),
        ),
        migrations.AddField(
            model_name='islandgame',
            name='winner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='won_island_games', to='islands.islandplayer'),
        ),
        migrations.CreateModel(
            name='Formation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slot', models.PositiveSmallIntegerField()),
                ('size', models.PositiveSmallIntegerField()),
                ('start_row', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('start_col', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('orientation', models.CharField(blank=True, choices=[('H', 'Horizontale'), ('V', 'Verticale')], default='', max_length=1)),
                ('pokemon_card', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='island_formations', to='game.pokemoncard')),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='formations', to='islands.islandplayer')),
            ],
            options={
                'ordering': ['slot'],
            },
        ),
        migrations.CreateModel(
            name='Shot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('row', models.PositiveSmallIntegerField()),
                ('col', models.PositiveSmallIntegerField()),
                ('result', models.CharField(choices=[('MISS', 'Raté'), ('HIT', 'Touché'), ('CAPTURED', 'Capturé')], max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('formation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='hits', to='islands.formation')),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shots', to='islands.islandgame')),
                ('shooter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shots_fired', to='islands.islandplayer')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shots_received', to='islands.islandplayer')),
            ],
            options={
                'ordering': ['created_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='islandplayer',
            constraint=models.UniqueConstraint(fields=('game', 'user'), name='unique_island_user_per_game'),
        ),
        migrations.AddConstraint(
            model_name='islandplayer',
            constraint=models.UniqueConstraint(fields=('game', 'turn_order'), name='unique_island_turn_order'),
        ),
        migrations.AddConstraint(
            model_name='islandplayer',
            constraint=models.CheckConstraint(condition=models.Q(('turn_order__in', (0, 1))), name='island_turn_order_zero_or_one'),
        ),
        migrations.AddConstraint(
            model_name='formation',
            constraint=models.UniqueConstraint(fields=('player', 'slot'), name='unique_island_formation_slot'),
        ),
        migrations.AddConstraint(
            model_name='formation',
            constraint=models.UniqueConstraint(fields=('player', 'pokemon_card'), name='unique_island_formation_pokemon'),
        ),
        migrations.AddConstraint(
            model_name='formation',
            constraint=models.CheckConstraint(condition=models.Q(('slot__gte', 0), ('slot__lt', 4)), name='island_formation_slot_range'),
        ),
        migrations.AddConstraint(
            model_name='formation',
            constraint=models.CheckConstraint(condition=models.Q(('size__in', (2, 3, 4))), name='island_formation_size_allowed'),
        ),
        migrations.AddConstraint(
            model_name='formation',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('orientation', ''), ('start_col__isnull', True), ('start_row__isnull', True)), models.Q(('orientation__in', ('H', 'V')), ('start_col__gte', 0), ('start_col__lt', 8), ('start_row__gte', 0), ('start_row__lt', 8)), _connector='OR'), name='island_formation_placement_shape'),
        ),
        migrations.AddConstraint(
            model_name='shot',
            constraint=models.UniqueConstraint(fields=('game', 'target', 'row', 'col'), name='unique_island_shot_per_target_cell'),
        ),
        migrations.AddConstraint(
            model_name='shot',
            constraint=models.CheckConstraint(condition=models.Q(('col__gte', 0), ('col__lt', 8), ('row__gte', 0), ('row__lt', 8)), name='island_shot_coordinate_range'),
        ),
        migrations.AddConstraint(
            model_name='shot',
            constraint=models.CheckConstraint(condition=models.Q(('shooter', models.F('target')), _negated=True), name='island_shot_distinct_players'),
        ),
        migrations.AddConstraint(
            model_name='shot',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('formation__isnull', True), ('result', 'MISS')), models.Q(('formation__isnull', False), ('result__in', ('HIT', 'CAPTURED'))), _connector='OR'), name='island_shot_result_matches_formation'),
        ),
    ]
