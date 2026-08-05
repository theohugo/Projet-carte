from django.utils.translation import get_language, gettext


def is_english() -> bool:
    return (get_language() or "fr").lower().startswith("en")


def text(french: str, english: str) -> str:
    """Use gettext catalogs when present, with an explicit English fallback."""

    translated = gettext(french)
    return english if is_english() and translated == french else translated


def pokemon_name(card) -> str:
    return card.name_en if is_english() else card.name_fr


def javascript_catalog() -> dict:
    pairs = {
        "load_error": (
            "Le plateau n’a pas pu être chargé. Recharge la page.",
            "The board could not be loaded. Refresh the page.",
        ),
        "race": ("Course", "Race"),
        "status_waiting": ("En préparation", "Preparing"),
        "status_running": ("Course en cours", "Race in progress"),
        "status_finished": ("Terminée", "Finished"),
        "synced": ("Synchronisé", "Synced"),
        "sending": ("Envoi…", "Sending…"),
        "refresh": ("À actualiser", "Refresh needed"),
        "updating": ("Actualisation…", "Updating…"),
        "offline": ("Hors ligne", "Offline"),
        "ready": ("prêt", "ready"),
        "computer": ("IA", "CPU"),
        "remove_bot": ("Retirer", "Remove"),
        "remove_bot_aria": ("Retirer {player} de la course", "Remove {player} from the race"),
        "open_seat": ("Place libre", "Open seat"),
        "waiting": ("En attente…", "Waiting…"),
        "trainers_ready": ("{count} dresseurs prêts. En avant !", "{count} trainers ready. Let's race!"),
        "need_trainer": ("Il faut encore un dresseur.", "One more trainer is needed."),
        "pawn_home": ("{starter}, pion {number}, au camp", "{starter}, pawn {number}, at camp"),
        "pawn_finished": (
            "{starter}, pion {number}, arrivé à la Ligue",
            "{starter}, pawn {number}, at the League",
        ),
        "pawn_lane": (
            "{starter}, pion {number}, couloir final case {cell}",
            "{starter}, pawn {number}, final lane space {cell}",
        ),
        "pawn_track": ("{starter}, pion {number}, case {cell}", "{starter}, pawn {number}, space {cell}"),
        "move_pawn": ("Déplacer ce pion.", "Move this pawn."),
        "cell": ("Case {cell}", "Space {cell}"),
        "safe": ("refuge", "safe space"),
        "shortcut_to": ("raccourci vers la case {cell}", "shortcut to space {cell}"),
        "start_of": ("départ de {starter}", "{starter}'s start"),
        "arrived": ("{count}/4 arrivés", "{count}/4 finished"),
        "team": ("{starter} · équipe {color}", "{starter} · {color} team"),
        "camp_lane": (
            "Camp et couloir final de {player}",
            "{player}'s camp and final lane",
        ),
        "color_leaf": ("verte", "green"),
        "color_flame": ("rouge", "red"),
        "color_wave": ("bleue", "blue"),
        "color_spark": ("jaune", "yellow"),
        "league_progress": ("{count}/4 à la Ligue", "{count}/4 at the League"),
        "your_roll": ("À toi de lancer !", "Your roll!"),
        "six_help": (
            "Un 6 fait sortir un Starter et te permet de rejouer.",
            "A 6 releases a Starter and lets you roll again.",
        ),
        "you_rolled": ("Tu as fait {roll}", "You rolled {roll}"),
        "choose_glowing": (
            "Choisis un pion illuminé sur le plateau ou dans ton camp.",
            "Choose a glowing pawn on the board or in your camp.",
        ),
        "player_rolled": ("{player} a fait {roll}", "{player} rolled {roll}"),
        "choosing_move": (
            "{starter} choisit son prochain mouvement.",
            "{starter} is choosing the next move.",
        ),
        "players_turn": ("Au tour de {player}", "{player}'s turn"),
        "about_to_roll": ("{starter} s’apprête à lancer le dé.", "{starter} is about to roll."),
        "roll_die": ("Lance le dé", "Roll the die"),
        "roll_help": ("Clique sur le dé pour avancer.", "Select the die to move."),
        "choose_to_move": ("Choisis pour avancer de {roll}", "Choose a pawn to move {roll}"),
        "available_pawn_one": ("1 pion disponible.", "1 pawn available."),
        "available_pawn_many": ("{count} pions disponibles.", "{count} pawns available."),
        "action_turn": ("Tour de {player}", "{player}'s turn"),
        "board_updates": (
            "Le plateau se mettra à jour automatiquement.",
            "The board will update automatically.",
        ),
        "no_move": (
            "{player} a lancé {roll}, mais aucun pion ne pouvait avancer.",
            "{player} rolled {roll}, but no pawn could move.",
        ),
        "new_try": ("Le 6 lui offre une nouvelle tentative.", "The 6 grants another try."),
        "enters_track": (
            "{player} fait entrer son pion {pawn} en piste avec un 6.",
            "{player} brings pawn {pawn} onto the track with a 6.",
        ),
        "moves_space_one": (
            "{player} avance son pion {pawn} d’une case.",
            "{player} moves pawn {pawn} 1 space.",
        ),
        "moves_space_many": (
            "{player} avance son pion {pawn} de {roll} cases.",
            "{player} moves pawn {pawn} {roll} spaces.",
        ),
        "takes_shortcut": ("Raccourci jusqu’à la case {cell} !", "Shortcut to space {cell}!"),
        "captured_one": ("{players} retourne au camp.", "{players} returns to camp."),
        "captured_many": ("{players} retournent au camp.", "{players} return to camp."),
        "reaches_league": ("Un Starter atteint la Ligue !", "A Starter reaches the League!"),
        "roll_again": ("Le 6 permet de rejouer.", "The 6 grants another roll."),
        "winner": ("{player} remporte la Ligue !", "{player} wins the League!"),
        "winner_copy": (
            "{starter} et ses quatre coéquipiers ont franchi l’arrivée avant toutes les autres équipes.",
            "{starter} and all four teammates reached the finish before every other team.",
        ),
        "action_failed": ("Cette action n’a pas pu être effectuée.", "This action could not be completed."),
        "turn_passed": (
            "Aucun pion ne pouvait avancer : le tour est passé.",
            "No pawn could move, so the turn passed.",
        ),
        "roll_announce": ("Tu as lancé {roll}. Choisis un pion.", "You rolled {roll}. Choose a pawn."),
        "pawn_moved": ("Le pion a avancé.", "The pawn moved."),
        "link_copied": ("Lien copié !", "Link copied!"),
        "copy_link": ("Copier le lien", "Copy link"),
        "copy_fallback": (
            "Copie le lien affiché dans la barre d’adresse.",
            "Copy the link shown in the address bar.",
        ),
        "sync_interrupted": ("Synchronisation interrompue.", "Sync interrupted."),
    }
    return {key: text(french, english) for key, (french, english) in pairs.items()}
