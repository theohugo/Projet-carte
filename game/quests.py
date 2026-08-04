"""Quêtes quotidiennes et hebdomadaires, et points qu'elles rapportent.

Le suivi passe par des évènements de jeu (``record_event``) que les quatre
moteurs déclenchent au moment utile. Chaque quête est décrite une fois ici :
les vues n'ont qu'à lire ``quest_board`` et à encaisser les récompenses.

La remise à zéro est implicite : une quête est stockée avec la période qu'elle
concerne (le jour ou la semaine ISO), donc changer de journée suffit à repartir
de zéro, sans tâche planifiée.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from game.models import Profile, QuestProgress


@dataclass(frozen=True, slots=True)
class Quest:
    key: str
    label: str
    description: str
    event: str
    target: int
    reward: int
    period: str  # "daily" ou "weekly"


# Les évènements suivis, alimentés par les moteurs de jeu.
EVENT_GAME_PLAYED = "game_played"
EVENT_GAME_WON = "game_won"
EVENT_SILHOUETTE_FOUND = "silhouette_found"
EVENT_PICTIONARY_FOUND = "pictionary_found"
EVENT_PICTIONARY_DRAWN = "pictionary_drawn"

QUESTS = (
    Quest(
        key="daily_play_three",
        label="Sur tous les fronts",
        description="Termine 3 parties, quel que soit le jeu.",
        event=EVENT_GAME_PLAYED,
        target=3,
        reward=60,
        period="daily",
    ),
    Quest(
        key="daily_win_one",
        label="Première victoire",
        description="Gagne une partie aujourd'hui.",
        event=EVENT_GAME_WON,
        target=1,
        reward=80,
        period="daily",
    ),
    Quest(
        key="daily_silhouettes",
        label="Œil de lynx",
        description="Reconnais 5 silhouettes.",
        event=EVENT_SILHOUETTE_FOUND,
        target=5,
        reward=70,
        period="daily",
    ),
    Quest(
        key="daily_drawing",
        label="Coup de crayon",
        description="Fais deviner un de tes dessins au Pictionary.",
        event=EVENT_PICTIONARY_DRAWN,
        target=1,
        reward=60,
        period="daily",
    ),
    Quest(
        key="weekly_marathon",
        label="Marathon",
        description="Termine 15 parties cette semaine.",
        event=EVENT_GAME_PLAYED,
        target=15,
        reward=260,
        period="weekly",
    ),
    Quest(
        key="weekly_champion",
        label="Champion de la semaine",
        description="Remporte 5 parties.",
        event=EVENT_GAME_WON,
        target=5,
        reward=320,
        period="weekly",
    ),
    Quest(
        key="weekly_guesser",
        label="Devineur infatigable",
        description="Trouve 25 Pokémon, silhouette ou dessin.",
        event=EVENT_SILHOUETTE_FOUND,
        target=25,
        reward=280,
        period="weekly",
    ),
)

QUESTS_BY_KEY = {quest.key: quest for quest in QUESTS}
# Le Pictionary et la silhouette nourrissent la même quête hebdomadaire : on
# devine un Pokémon dans les deux cas.
EVENT_ALIASES = {EVENT_PICTIONARY_FOUND: (EVENT_PICTIONARY_FOUND, EVENT_SILHOUETTE_FOUND)}


def period_key(quest: Quest, moment=None) -> str:
    """Identifiant de la période en cours pour cette quête."""

    moment = moment or timezone.localtime()
    if quest.period == "weekly":
        iso = moment.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return moment.strftime("%Y-%m-%d")


def record_event(user, event: str, amount: int = 1) -> None:
    """Fait avancer toutes les quêtes concernées par cet évènement.

    Silencieux pour un utilisateur absent (partie contre une IA, joueur
    supprimé) : le suivi de quêtes ne doit jamais interrompre une partie.
    """

    if user is None or not getattr(user, "is_authenticated", True) or amount <= 0:
        return

    events = EVENT_ALIASES.get(event, (event,))
    for quest in QUESTS:
        if quest.event not in events:
            continue
        progress, _ = QuestProgress.objects.get_or_create(
            user=user,
            quest_key=quest.key,
            period_key=period_key(quest),
        )
        if progress.claimed_at is not None or progress.progress >= quest.target:
            continue
        QuestProgress.objects.filter(pk=progress.pk).update(progress=F("progress") + amount)


def _progress_map(user) -> dict[str, QuestProgress]:
    keys = {quest.key: period_key(quest) for quest in QUESTS}
    rows = QuestProgress.objects.filter(user=user, quest_key__in=keys)
    return {row.quest_key: row for row in rows if keys[row.quest_key] == row.period_key}


def quest_board(user) -> dict:
    """État des quêtes du joueur, prêt à afficher."""

    rows = _progress_map(user)
    board = {"daily": [], "weekly": [], "claimable": 0}
    for quest in QUESTS:
        row = rows.get(quest.key)
        progress = min(row.progress, quest.target) if row else 0
        claimed = bool(row and row.claimed_at)
        is_complete = progress >= quest.target
        if is_complete and not claimed:
            board["claimable"] += 1
        board[quest.period].append(
            {
                "key": quest.key,
                "label": quest.label,
                "description": quest.description,
                "reward": quest.reward,
                "target": quest.target,
                "progress": progress,
                "percent": round(100 * progress / quest.target),
                "is_complete": is_complete,
                "claimed": claimed,
                "claimable": is_complete and not claimed,
            }
        )
    return board


class QuestError(Exception):
    """Récompense impossible à encaisser."""


@transaction.atomic
def claim_reward(user, quest_key: str) -> int:
    """Encaisse une quête terminée et crédite ses points. Renvoie le gain."""

    quest = QUESTS_BY_KEY.get(quest_key)
    if quest is None:
        raise QuestError("Cette quête n'existe pas.")

    progress = (
        QuestProgress.objects.select_for_update()
        .filter(user=user, quest_key=quest.key, period_key=period_key(quest))
        .first()
    )
    if progress is None or progress.progress < quest.target:
        raise QuestError("Cette quête n'est pas encore terminée.")
    if progress.claimed_at is not None:
        raise QuestError("Récompense déjà récupérée.")

    progress.claimed_at = timezone.now()
    progress.save(update_fields=["claimed_at"])
    Profile.objects.filter(user=user).update(points=F("points") + quest.reward)
    return quest.reward
