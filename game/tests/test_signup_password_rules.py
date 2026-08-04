from django.test import TestCase
from django.urls import reverse

from game.forms import SignUpForm
from game.password_rules import MISSING, PENDING, SATISFIED


def rule_states(form):
    return {rule.code: rule.state for rule in form.password_rules}


class PasswordRulesTests(TestCase):
    def test_unbound_form_lists_every_rule_as_pending(self):
        states = rule_states(SignUpForm())

        self.assertEqual(
            set(states),
            {"length", "not-numeric", "not-similar", "not-common", "match"},
        )
        self.assertEqual(set(states.values()), {PENDING})

    def test_too_short_password_marks_only_the_length_rule(self):
        form = SignUpForm({"username": "sacha", "password1": "Kk-2!", "password2": "Kk-2!"})

        states = rule_states(form)

        self.assertFalse(form.is_valid())
        self.assertEqual(states["length"], MISSING)
        self.assertEqual(states["not-numeric"], SATISFIED)
        self.assertEqual(states["match"], SATISFIED)

    def test_numeric_and_common_passwords_are_reported(self):
        form = SignUpForm({"username": "sacha", "password1": "12345678", "password2": "12345678"})

        states = rule_states(form)

        self.assertFalse(form.is_valid())
        self.assertEqual(states["not-numeric"], MISSING)
        self.assertEqual(states["not-common"], MISSING)
        self.assertEqual(states["length"], SATISFIED)

    def test_password_similar_to_the_username_is_reported(self):
        form = SignUpForm(
            {
                "username": "dracaufeu",
                "password1": "dracaufeu-2",
                "password2": "dracaufeu-2",
            }
        )

        states = rule_states(form)

        self.assertFalse(form.is_valid())
        self.assertEqual(states["not-similar"], MISSING)

    def test_mismatched_confirmation_is_reported(self):
        form = SignUpForm(
            {
                "username": "sacha",
                "password1": "A-very-safe-password-2026!",
                "password2": "A-very-safe-password-2027!",
            }
        )

        states = rule_states(form)

        self.assertFalse(form.is_valid())
        self.assertEqual(states["match"], MISSING)
        self.assertEqual(states["length"], SATISFIED)


class SignupPageTests(TestCase):
    def test_checklist_is_displayed_on_the_signup_page(self):
        response = self.client.get(reverse("signup"))

        self.assertContains(response, "Pour être accepté, le mot de passe doit respecter")
        self.assertContains(response, 'data-rule="length"')
        self.assertContains(response, 'data-min-length="8"')

    def test_failed_submission_highlights_the_missing_rules(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "sacha", "password1": "12345678", "password2": "12345678"},
        )

        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertRegex(content, r'password-rule is-missing"\s+data-rule="not-numeric"')
        self.assertRegex(content, r'password-rule is-missing"\s+data-rule="not-common"')
        self.assertRegex(content, r'password-rule is-satisfied"\s+data-rule="length"')
