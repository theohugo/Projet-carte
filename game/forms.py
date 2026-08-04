from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from game.password_rules import build_password_rules, failed_rule_codes


class SignUpForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        )
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        # La checklist du gabarit remplace les aides textuelles par défaut.
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    @property
    def password_rules(self):
        """Règles de mot de passe, marquées d'après les erreurs de la soumission."""

        if not self.is_bound:
            return build_password_rules()
        return build_password_rules(
            failed_codes=failed_rule_codes(self.errors.as_data()),
            evaluated=bool(self.data.get("password1")),
        )

    class Meta:
        model = User
        fields = ["username"]
