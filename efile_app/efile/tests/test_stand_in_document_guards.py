"""The guards that keep the EFSP stand-in document out of a real filing.

`substitute_test_document_urls` replaces every document in a filing payload with
a fixed PDF so fee quotes work locally, where the EFSP proxy cannot reach a
LocalStack URL. Reaching a real court, it would file a placeholder in place of
someone's actual document, so three independent layers have to fail before that
can happen. Each is tested here; test_efsp_payload.py covers the substitution
behaviour itself.
"""

import importlib
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from efile.checks import efsp_stand_in_document_is_development_only

STAND_IN_URL = "https://example.org/fixtures/blank.pdf"


# --- Layer 1: settings_dev refuses to load on a deployed host ----------------


def test_dev_settings_refuse_to_load_on_a_deployed_host(monkeypatch):
    """manage.py/wsgi.py/asgi.py all fall back to efile.settings, which is dev.

    A deploy that loses DJANGO_SETTINGS_MODULE would otherwise come up with
    DEBUG=True, where every DEBUG-keyed guard below is inert.
    """
    monkeypatch.setenv("FLY_APP_NAME", "forms-mvp-staging")

    import efile.settings_dev

    with pytest.raises(ImproperlyConfigured, match="deployed host"):
        importlib.reload(efile.settings_dev)


def test_dev_settings_load_normally_off_a_deployed_host(monkeypatch):
    monkeypatch.delenv("FLY_APP_NAME", raising=False)

    import efile.settings_dev

    importlib.reload(efile.settings_dev)  # must not raise


# --- Layer 2: the startup system check ---------------------------------------


def test_check_errors_when_stand_in_is_set_outside_debug():
    with override_settings(EFSP_TEST_DOCUMENT_URL=STAND_IN_URL, DEBUG=False):
        messages = efsp_stand_in_document_is_development_only(None)

    assert [m.id for m in messages] == ["efile.E001"]


def test_check_is_silent_when_stand_in_is_unset():
    """The production configuration must produce no noise at all."""
    with override_settings(EFSP_TEST_DOCUMENT_URL="", DEBUG=False):
        assert efsp_stand_in_document_is_development_only(None) == []


def test_check_warns_while_the_stand_in_is_active_in_development():
    """Active substitution is announced at startup rather than only per-request."""
    with override_settings(EFSP_TEST_DOCUMENT_URL=STAND_IN_URL, DEBUG=True):
        messages = efsp_stand_in_document_is_development_only(None)

    assert [m.id for m in messages] == ["efile.W001"]
    assert STAND_IN_URL in messages[0].msg


def test_check_is_registered_so_it_runs_on_management_commands():
    from django.core.checks import registry

    assert efsp_stand_in_document_is_development_only in registry.registry.get_checks()


# --- Layer 3: deployed settings modules never read the variable ---------------


def test_the_setting_is_only_ever_read_in_dev_settings():
    """Exporting EFSP_TEST_DOCUMENT_URL in staging or production must do nothing.

    Checked against the source rather than by importing settings_prod and
    settings_staging, which refuse to import without a production secret key and
    DATABASE_URL. The property being protected is exactly a textual one: no
    settings module other than settings_dev may read this environment variable.
    """
    settings_dir = Path(__file__).resolve().parent.parent
    readers = sorted(
        path.name for path in settings_dir.glob("settings*.py") if "EFSP_TEST_DOCUMENT_URL" in path.read_text()
    )

    assert readers == ["settings_dev.py"]
