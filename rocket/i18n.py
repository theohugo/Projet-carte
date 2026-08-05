from django.utils.translation import get_language, gettext


def is_english() -> bool:
    return (get_language() or "fr").lower().startswith("en")


def text(french: str, english: str) -> str:
    translated = gettext(french)
    return english if is_english() and translated == french else translated


def status_label(status: str) -> str:
    labels = {
        "EN_ATTENTE": ("En attente", "Waiting"),
        "NUIT": ("Nuit", "Night"),
        "DISCUSSION": ("Discussion", "Discussion"),
        "VOTE": ("Vote", "Vote"),
        "TERMINEE": ("Terminée", "Finished"),
    }
    french, english = labels.get(status, (status, status))
    return text(french, english)


def winner_label(side: str) -> str:
    labels = {
        "ALLIES": ("Alliance des Dresseurs", "Trainer Alliance"),
        "ROCKET": ("Team Rocket", "Team Rocket"),
    }
    french, english = labels.get(side, (side, side))
    return text(french, english)


def role_presentation(role: str) -> dict:
    roles = {
        "ROCKET": {
            "name": ("Agent Rocket", "Team Rocket Agent"),
            "side": ("Team Rocket", "Team Rocket"),
            "mission": (
                "Sabote un Dresseur chaque nuit et reste indétectable pendant les votes.",
                "Sabotage a Trainer each night and stay undetected during votes.",
            ),
        },
        "DETECTIVE": {
            "name": ("Détective Looker", "Detective Looker"),
            "side": ("Alliance des Dresseurs", "Trainer Alliance"),
            "mission": (
                "Enquête chaque nuit sur un joueur pour savoir s'il appartient à la Team Rocket.",
                "Investigate one player each night to learn whether they belong to Team Rocket.",
            ),
        },
        "GUARDIAN": {
            "name": ("Leuphorie gardienne", "Guardian Blissey"),
            "side": ("Alliance des Dresseurs", "Trainer Alliance"),
            "mission": (
                "Protège un joueur chaque nuit contre le sabotage de la Team Rocket.",
                "Protect one player each night from Team Rocket's sabotage.",
            ),
        },
        "TRAINER": {
            "name": ("Dresseur", "Trainer"),
            "side": ("Alliance des Dresseurs", "Trainer Alliance"),
            "mission": (
                "Observe les débats, repère les incohérences et vote pour démasquer les agents.",
                "Watch the debate, spot inconsistencies, and vote to expose the agents.",
            ),
        },
    }
    presentation = roles[role]
    return {key: text(french, english) for key, (french, english) in presentation.items()}


def javascript_catalog() -> dict:
    pairs = {
        "general_error": ("Une erreur est survenue.", "Something went wrong."),
        "action_denied": ("Action refusée.", "Action denied."),
        "eliminated": ("Éliminé", "Eliminated"),
        "vote_saved": ("Vote enregistré", "Vote saved"),
        "you": ("Toi", "You"),
        "on_mission": ("En mission", "On mission"),
        "choose_player": ("Choisir {player}", "Choose {player}"),
        "agent_number": ("AGENT {number}", "AGENT {number}"),
        "no_report": ("Aucun rapport pour l’instant.", "No reports yet."),
        "night_report": ("Nuit {round} · {player} : {side}", "Night {round} · {player}: {side}"),
        "alliance_short": ("Alliance", "Alliance"),
        "blocked_event": (
            "Le sabotage de la Team Rocket a été bloqué pendant la nuit.",
            "Team Rocket's sabotage was blocked during the night.",
        ),
        "night_elimination": (
            "{player} a été éliminé pendant la nuit.",
            "{player} was eliminated during the night.",
        ),
        "no_victim": ("La nuit s’est achevée sans victime.", "The night ended with no victim."),
        "vote_tie": (
            "Le conseil s’est terminé sur une égalité : personne n’est éliminé.",
            "The council ended in a tie: nobody was eliminated.",
        ),
        "vote_elimination": (
            "{player} a été éliminé par le conseil.",
            "{player} was eliminated by the council.",
        ),
        "vote_finished": ("Le vote est terminé.", "The vote is over."),
        "night_round": ("Nuit {round}", "Night {round}"),
        "day_round": ("Jour {round}", "Day {round}"),
        "observe_title": ("Observe la mission.", "Watch the mission."),
        "observe_text": (
            "Tu es éliminé : les actions restantes se déroulent sans toi.",
            "You were eliminated; the remaining actions continue without you.",
        ),
        "kill_title": ("Choisis une cible à saboter.", "Choose a target to sabotage."),
        "kill_text": (
            "Les agents Rocket votent pendant la nuit. En cas d’égalité, la cible la plus ancienne dans l’escouade est retenue.",
            "Team Rocket agents choose during the night. On a tie, the earliest target in the squad is selected.",
        ),
        "inspect_title": ("Ouvre une enquête secrète.", "Open a secret investigation."),
        "inspect_text": (
            "Choisis un joueur : son camp sera ajouté à tes rapports privés.",
            "Choose a player; their side will be added to your private reports.",
        ),
        "protect_title": ("Place ta protection.", "Place your protection."),
        "protect_text": (
            "Choisis n’importe quel survivant, toi compris. Une attaque contre lui sera annulée.",
            "Choose any survivor, including yourself. An attack against them will be cancelled.",
        ),
        "sleep_title": ("La ville s’endort…", "The city falls asleep…"),
        "sleep_text": (
            "Ton rôle n’agit pas la nuit. Attends que les rôles spéciaux terminent leur mission.",
            "Your role has no night action. Wait for the special roles to finish their mission.",
        ),
        "choice_locked": (
            "Ton choix est verrouillé · attente des autres rôles",
            "Your choice is locked · waiting for the other roles",
        ),
        "auto_resolution": (
            "Résolution automatique à la fin du délai",
            "Automatic resolution when time expires",
        ),
        "find_title": ("Débusque les infiltrés.", "Find the infiltrators."),
        "listen_title": ("Écoute le débat.", "Listen to the debate."),
        "discussion_alive": (
            "Compare les versions, partage tes indices sans dévoiler trop vite ton rôle, puis ouvre le conseil quand le groupe est prêt.",
            "Compare stories and share clues without revealing your role too soon, then open the council when the group is ready.",
        ),
        "discussion_dead": (
            "Tu peux lire les échanges, mais les joueurs éliminés ne peuvent plus intervenir.",
            "You can read the discussion, but eliminated players can no longer take part.",
        ),
        "council": ("Conseil en cours", "Council in progress"),
        "vote_title": ("Vote contre un suspect.", "Vote against a suspect."),
        "deliberating": ("Le conseil délibère.", "The council is deliberating."),
        "vote_alive": (
            "Ton bulletin reste secret jusqu’à la résolution. Tu peux changer de cible tant que tous les survivants n’ont pas voté.",
            "Your ballot stays secret until resolution. You may change target until every survivor has voted.",
        ),
        "vote_dead": (
            "Les survivants choisissent le prochain joueur éliminé.",
            "The survivors are choosing the next eliminated player.",
        ),
        "ballots": ("{submitted}/{required} bulletins déposés", "{submitted}/{required} ballots cast"),
        "declassified": ("Dossiers déclassifiés", "Declassified files"),
        "roles_revealed": ("Tous les rôles sont révélés.", "Every role is revealed."),
        "rebuild_bluffs": (
            "L’escouade peut maintenant reconstituer chaque bluff de la mission.",
            "The squad can now reconstruct every bluff from the mission.",
        ),
        "winner": ("{side} gagne", "{side} wins"),
        "team_won": ("Ton camp remporte cette infiltration.", "Your side wins this infiltration."),
        "team_lost": (
            "Ton camp a été démasqué. La revanche t’attend.",
            "Your side was exposed. A rematch awaits.",
        ),
        "chat_empty": (
            "Le canal est silencieux. Qui prendra la parole en premier ?",
            "The channel is quiet. Who will speak first?",
        ),
        "players_count": ("{count} joueurs", "{count} players"),
        "cycle": ("Cycle {round}", "Cycle {round}"),
        "minimum_one": ("1 joueur encore nécessaire pour démarrer.", "1 more player is needed to start."),
        "minimum_many": (
            "{count} joueurs encore nécessaires pour démarrer.",
            "{count} more players are needed to start.",
        ),
        "squad_ready": (
            "Escouade suffisante : l’hôte peut lancer la mission.",
            "The squad is ready: the host can start the mission.",
        ),
        "room_announce": ("{count} joueurs dans le salon.", "{count} players in the room."),
        "survivor_one": ("1 survivant", "1 survivor"),
        "survivor_many": ("{count} survivants", "{count} survivors"),
        "phase_announce": (
            "{phase}, cycle {round}. {report}",
            "{phase}, cycle {round}. {report}",
        ),
        "link_copied": ("Lien copié", "Link copied"),
        "copy_failed": (
            "Impossible de copier automatiquement le lien.",
            "The link could not be copied automatically.",
        ),
    }
    return {key: text(french, english) for key, (french, english) in pairs.items()}
