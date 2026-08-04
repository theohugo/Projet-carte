from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from game.models import Profile
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

        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    @property
    def password_rules(self):
        if not self.is_bound:
            return build_password_rules()

        return build_password_rules(
            failed_codes=failed_rule_codes(self.errors.as_data()),
            evaluated=bool(self.data.get("password1")),
        )

    class Meta:
        model = User
        fields = ["username"]


class AccountForm(forms.ModelForm):
    """Modification des informations principales du compte."""

    email = forms.EmailField(
        required=True,
        label="Adresse e-mail",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "exemple@email.fr",
            }
        ),
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        labels = {
            "username": "Nom d’utilisateur",
            "first_name": "Prénom",
            "last_name": "Nom",
        }
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "autocomplete": "username",
                    "autocapitalize": "none",
                    "spellcheck": "false",
                }
            ),
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        email_already_used = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists()

        if email_already_used:
            raise ValidationError("Cette adresse e-mail est déjà utilisée par un autre compte.")

        return email


class ProfileForm(forms.ModelForm):
    """Modification de la photo et de la description du profil."""

    class Meta:
        model = Profile
        fields = ["avatar", "description"]
        labels = {
            "avatar": "Photo de profil",
            "description": "Description",
        }
        widgets = {
            "avatar": forms.ClearableFileInput(
                attrs={
                    "accept": "image/png,image/jpeg,image/webp",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "maxlength": 500,
                    "placeholder": ("Présente-toi aux autres joueurs en quelques mots..."),
                }
            ),
        }
        help_texts = {
            "avatar": "Formats acceptés : JPG, PNG ou WebP. Taille maximale : 5 Mo.",
            "description": "500 caractères maximum.",
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")

        if not avatar:
            return avatar

        if avatar.size > 5 * 1024 * 1024:
            raise ValidationError("La photo de profil ne doit pas dépasser 5 Mo.")

        content_type = getattr(avatar, "content_type", "")
        allowed_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if content_type and content_type not in allowed_types:
            raise ValidationError("Utilise une image au format JPG, PNG ou WebP.")

        return avatar
