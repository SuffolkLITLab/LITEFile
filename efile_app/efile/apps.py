from django.apps import AppConfig


class EfileConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "efile"
    verbose_name = "LITEFile"

    def ready(self):
        # Registers the checks in efile/checks.py by importing them.
        from efile import (
            checks,  # noqa: F401
            signals,  # noqa: F401
        )
