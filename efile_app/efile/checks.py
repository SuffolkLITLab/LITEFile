"""Startup system checks.

These run on every management command -- including the ``manage.py migrate`` that
fly.toml uses as its release command -- so a misconfiguration fails the deploy
instead of waiting to be discovered by a filing.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def efsp_stand_in_document_is_development_only(app_configs, **kwargs):
    """EFSP_TEST_DOCUMENT_URL must never be active outside local development.

    When set, every document in a filing payload is replaced by a stand-in PDF
    before the payload reaches the EFSP proxy. That is indispensable locally,
    where the proxy cannot fetch a LocalStack URL, and unacceptable anywhere a
    filing might reach a real court.

    Reported as an Error (which blocks the command) rather than a Warning: the
    correct response to finding this in production is to stop, not to continue
    and hope the request-time guard in efsp_payload catches it.
    """
    stand_in_url = getattr(settings, "EFSP_TEST_DOCUMENT_URL", "")
    if not stand_in_url:
        return []

    if not settings.DEBUG:
        return [
            Error(
                "EFSP_TEST_DOCUMENT_URL is set while DEBUG is False.",
                hint=(
                    "This replaces every filed document with a stand-in PDF. It is a "
                    "local-development affordance only. Unset EFSP_TEST_DOCUMENT_URL, and "
                    "confirm DJANGO_SETTINGS_MODULE points at efile.settings_staging or "
                    "efile.settings_prod rather than falling back to efile.settings (dev)."
                ),
                id="efile.E001",
            )
        ]

    return [
        Warning(
            f"EFSP_TEST_DOCUMENT_URL is active: filings will send {stand_in_url} in place of every uploaded document.",
            hint=(
                "Fee quotes and submissions from this process do not reflect real "
                "documents. Unset it to send real S3 URLs to the EFSP proxy."
            ),
            id="efile.W001",
        )
    ]


@register()
def configured_ui_text_keys_are_known(app_configs, **kwargs):
    """Every ``text:`` key in a state's YAML must name a real UI string.

    A state file is the one place where user-facing copy is written by someone
    who is not looking at the templates, so a typo -- or a key that a later
    refactor renamed -- would otherwise fail silently: the override is ignored
    and the filer keeps reading the default wording, which is exactly the
    wording the state asked to change.

    A Warning rather than an Error: the app is still safe to serve, and a deploy
    should not be blocked by a paragraph that reverts to its default.
    """
    from efile.utils.config_loader import config_loader
    from efile.utils.ui_text import UI_STRINGS, config_overrides

    problems = []
    for jurisdiction in config_loader.get_available_jurisdictions():
        config = config_loader.load_jurisdiction_config(jurisdiction) or {}
        for key in sorted(config_overrides(config)):
            if key not in UI_STRINGS:
                problems.append(
                    Warning(
                        f"{jurisdiction}.yaml sets text.{key}, which is not a known UI text key.",
                        hint=(
                            "Check the spelling against the keys in efile/utils/ui_text.py, or add "
                            "the key there with an English default if this is new copy."
                        ),
                        id="efile.W002",
                    )
                )
    return problems
