import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0017_card_prints_and_rarities'),
        ('guesswho', '0001_initial'),
        ('islands', '0001_initial'),
        ('metamorph', '0001_initial'),
        ('pictionary', '0001_initial'),
        ('rocket', '0002_rocketgame_phase_deadline'),
        ('silhouette', '0001_initial'),
        ('starterrace', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='gameinvitation',
            name='game_invitation_has_one_valid_room',
        ),
        migrations.AddField(
            model_name='gameinvitation',
            name='islands_game',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='islands.islandgame'),
        ),
        migrations.AddField(
            model_name='gameinvitation',
            name='metamorph_game',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='metamorph.metamorphgame'),
        ),
        migrations.AddField(
            model_name='gameinvitation',
            name='rocket_game',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='rocket.rocketgame'),
        ),
        migrations.AddField(
            model_name='gameinvitation',
            name='starterrace_game',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='starterrace.game'),
        ),
        migrations.AlterField(
            model_name='gameinvitation',
            name='mode',
            field=models.CharField(choices=[('POKE_UNO', 'Poké-Uno'), ('GUESSWHO', 'Qui est-ce ?'), ('SILHOUETTE', 'Silhouette'), ('PICTIONARY', 'Pictionary'), ('METAMORPH', 'Métamorph Mystère'), ('ROCKET', 'Infiltration Rocket'), ('ISLANDS', 'Bataille des Îles'), ('STARTER_RACE', 'Course des Starters')], default='POKE_UNO', max_length=16),
        ),
        migrations.AddConstraint(
            model_name='gameinvitation',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('game__isnull', False), ('guesswho_game__isnull', True), ('islands_game__isnull', True), ('metamorph_game__isnull', True), ('mode', 'POKE_UNO'), ('pictionary_game__isnull', True), ('rocket_game__isnull', True), ('silhouette_game__isnull', True), ('starterrace_game__isnull', True)), models.Q(('game__isnull', True), ('guesswho_game__isnull', False), ('islands_game__isnull', True), ('metamorph_game__isnull', True), ('mode', 'GUESSWHO'), ('pictionary_game__isnull', True), ('rocket_game__isnull', True), ('silhouette_game__isnull', True), ('starterrace_game__isnull', True)), models.Q(('game__isnull', True), ('guesswho_game__isnull', True), ('islands_game__isnull', True), ('metamorph_game__isnull', True), ('mode', 'SILHOUETTE'), ('pictionary_game__isnull', True), ('rocket_game__isnull', True), ('silhouette_game__isnull', False), ('starterrace_game__isnull', True)), models.Q(('game__isnull', True), ('guesswho_game__isnull', True), ('islands_game__isnull', True), ('metamorph_game__isnull', True), ('mode', 'PICTIONARY'), ('pictionary_game__isnull', False), ('rocket_game__isnull', True), ('silhouette_game__isnull', True), ('starterrace_game__isnull', True)), models.Q(('game__isnull', True), ('guesswho_game__isnull', True), ('islands_game__isnull', True), ('metamorph_game__isnull', False), ('mode', 'METAMORPH'), ('pictionary_game__isnull', True), ('rocket_game__isnull', True), ('silhouette_game__isnull', True), ('starterrace_game__isnull', True)), models.Q(('game__isnull', True), ('guesswho_game__isnull', True), ('islands_game__isnull', True), ('metamorph_game__isnull', True), ('mode', 'ROCKET'), ('pictionary_game__isnull', True), ('rocket_game__isnull', False), ('silhouette_game__isnull', True), ('starterrace_game__isnull', True)), models.Q(('game__isnull', True), ('guesswho_game__isnull', True), ('islands_game__isnull', False), ('metamorph_game__isnull', True), ('mode', 'ISLANDS'), ('pictionary_game__isnull', True), ('rocket_game__isnull', True), ('silhouette_game__isnull', True), ('starterrace_game__isnull', True)), models.Q(('game__isnull', True), ('guesswho_game__isnull', True), ('islands_game__isnull', True), ('metamorph_game__isnull', True), ('mode', 'STARTER_RACE'), ('pictionary_game__isnull', True), ('rocket_game__isnull', True), ('silhouette_game__isnull', True), ('starterrace_game__isnull', False)), _connector='OR'), name='game_invitation_has_one_valid_room'),
        ),
        migrations.AddConstraint(
            model_name='gameinvitation',
            constraint=models.UniqueConstraint(condition=models.Q(('metamorph_game__isnull', False), ('status', 'PENDING')), fields=('metamorph_game', 'recipient'), name='unique_pending_metamorph_invitation'),
        ),
        migrations.AddConstraint(
            model_name='gameinvitation',
            constraint=models.UniqueConstraint(condition=models.Q(('rocket_game__isnull', False), ('status', 'PENDING')), fields=('rocket_game', 'recipient'), name='unique_pending_rocket_invitation'),
        ),
        migrations.AddConstraint(
            model_name='gameinvitation',
            constraint=models.UniqueConstraint(condition=models.Q(('islands_game__isnull', False), ('status', 'PENDING')), fields=('islands_game', 'recipient'), name='unique_pending_islands_invitation'),
        ),
        migrations.AddConstraint(
            model_name='gameinvitation',
            constraint=models.UniqueConstraint(condition=models.Q(('starterrace_game__isnull', False), ('status', 'PENDING')), fields=('starterrace_game', 'recipient'), name='unique_pending_starterrace_invitation'),
        ),
    ]
