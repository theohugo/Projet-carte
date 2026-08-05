"""Traduction des validateurs Django en règles lisibles pour l'écran d'inscription.

Les règles sont dérivées de `AUTH_PASSWORD_VALIDATORS` afin que la liste affichée
au joueur reste synchronisée avec ce que le serveur accepte réellement.
"""

from dataclasses import dataclass, field

from django.contrib.auth.password_validation import get_default_password_validators

from game.pokemon_names import bilingual_text

# Le serveur reste seul juge : `checked_client_side` indique simplement si
# `signup.js` sait évaluer la règle pendant la frappe.
PENDING = "pending"
SATISFIED = "satisfied"
MISSING = "missing"

# Du critère le plus simple à corriger au plus contextuel.
DISPLAY_ORDER = ["length", "not-numeric", "not-similar", "not-common", "match"]

# Codes d'erreur levés par les validateurs, associés à la règle correspondante.
ERROR_CODE_TO_RULE = {
    "password_too_short": "length",
    "password_entirely_numeric": "not-numeric",
    "password_too_similar": "not-similar",
    "password_too_common": "not-common",
    "password_mismatch": "match",
}


@dataclass
class PasswordRule:
    code: str
    label: str
    checked_client_side: bool = True
    parameters: dict = field(default_factory=dict)
    state: str = PENDING

    @property
    def min_length(self):
        return self.parameters.get("min_length")


def _rule_for(validator):
    name = type(validator).__name__
    if name == "MinimumLengthValidator":
        return PasswordRule(
            code="length",
            label=bilingual_text(
                f"Au moins {validator.min_length} caractères",
                f"At least {validator.min_length} characters",
            ),
            parameters={"min_length": validator.min_length},
        )
    if name == "NumericPasswordValidator":
        return PasswordRule(
            code="not-numeric",
            label=bilingual_text("Pas uniquement des chiffres", "Not entirely numeric"),
        )
    if name == "UserAttributeSimilarityValidator":
        return PasswordRule(
            code="not-similar",
            label=bilingual_text("Différent du nom d'utilisateur", "Different from your username"),
        )
    if name == "CommonPasswordValidator":
        return PasswordRule(
            code="not-common",
            label=bilingual_text(
                "Pas un mot de passe trop courant (vérifié à l'envoi)",
                "Not a commonly used password (checked on submit)",
            ),
            checked_client_side=False,
        )
    return None


def build_password_rules(failed_codes=frozenset(), evaluated=False):
    """Liste des règles à afficher, marquées selon les erreurs renvoyées par le serveur.

    `evaluated` vaut True lorsqu'un mot de passe a été soumis : les règles sans
    erreur associée sont alors considérées comme respectées.
    """

    rules = [rule for validator in get_default_password_validators() if (rule := _rule_for(validator))]
    rules.append(
        PasswordRule(
            code="match",
            label=bilingual_text("Les deux mots de passe sont identiques", "Both passwords match"),
        )
    )
    rules.sort(key=lambda rule: DISPLAY_ORDER.index(rule.code))

    for rule in rules:
        if rule.code in failed_codes:
            rule.state = MISSING
        elif evaluated:
            rule.state = SATISFIED

    return rules


def failed_rule_codes(errors_as_data):
    """Codes de règles en échec, extraits de `form.errors.as_data()`."""

    codes = set()
    for error_list in errors_as_data.values():
        for error in error_list:
            rule_code = ERROR_CODE_TO_RULE.get(error.code)
            if rule_code:
                codes.add(rule_code)
    return codes
