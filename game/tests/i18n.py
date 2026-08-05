from django.utils import translation


class LanguageIsolationMixin:
    """Keep LocaleMiddleware requests from leaking language into the next test."""

    def tearDown(self):
        translation.deactivate_all()
        super().tearDown()
