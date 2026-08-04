"""Suppression des comptes invités devenus inutiles.

Un invité est créé sans engagement : sans ménage, la table des utilisateurs
grossit à chaque visiteur. On ne supprime que les comptes inactifs depuis
``GUEST_RETENTION_DAYS`` et qui ne participent à aucune partie encore en cours.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from game.guests import GUEST_RETENTION_DAYS
from game.models import Game
from guesswho.models import GuessWhoGame
from pictionary.models import PictionaryGame
from silhouette.models import SilhouetteGame


class Command(BaseCommand):
    help = "Supprime les comptes invités inactifs et sans partie en cours."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=GUEST_RETENTION_DAYS,
            help=f"Ancienneté minimale, en jours (défaut : {GUEST_RETENTION_DAYS}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche ce qui serait supprimé sans rien supprimer.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timezone.timedelta(days=options["days"])
        guests = User.objects.filter(profile__is_guest=True, date_joined__lt=cutoff)

        busy = self._busy_guest_ids(guests)
        removable = guests.exclude(pk__in=busy)
        count = removable.count()

        if options["dry_run"]:
            self.stdout.write(f"{count} invités seraient supprimés ({len(busy)} encore en partie).")
            return

        removable.delete()
        self.stdout.write(
            self.style.SUCCESS(f"{count} invités supprimés ({len(busy)} conservés, encore en partie).")
        )

    @staticmethod
    def _busy_guest_ids(guests):
        """Invités encore attendus dans un salon ou une partie en cours."""

        en_cours = Q(status__in=["EN_ATTENTE", "EN_COURS", "CHOIX"])
        busy = set()
        for model in (Game, GuessWhoGame, SilhouetteGame, PictionaryGame):
            busy.update(
                model.objects.filter(en_cours, players__user__in=guests).values_list(
                    "players__user_id", flat=True
                )
            )
        return busy
