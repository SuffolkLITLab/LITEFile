"""Tests for the shared EFSP payload preparation.

The safety-critical property is that EFSP_TEST_DOCUMENT_URL is inert unless a
developer opts in, so the "off" cases are tested as carefully as the "on" ones.
"""

import logging

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from efile.services.efsp_payload import (
    prepare_efile_payload,
    resolve_placeholder_filing_components,
    substitute_test_document_urls,
)

REAL_S3_URL = "https://forms-mvp-xf6361.s3.us-east-1.amazonaws.com/efile-documents/lead/abc.pdf?X-Amz-Signature=x"
STAND_IN_URL = "https://example.org/fixtures/blank.pdf"


@pytest.fixture
def efile_logs(caplog):
    """Capture records from the ``efile`` logger.

    ``caplog`` only attaches to the root logger, and settings_base.LOGGING sets
    ``propagate: False`` on ``efile``, so its records never reach root.
    """
    logger = logging.getLogger("efile")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="efile")
    yield caplog
    logger.removeHandler(caplog.handler)


def _bundle(**overrides):
    bundle = {"data_url": REAL_S3_URL, "filing_type": "27965", "filing_component": "331"}
    bundle.update(overrides)
    return {"al_court_bundle": [bundle]}


# --- EFSP_TEST_DOCUMENT_URL off (the production configuration) ---------------


def test_real_document_url_is_untouched_when_stand_in_is_not_configured():
    efile_data = _bundle()

    with override_settings(EFSP_TEST_DOCUMENT_URL=""):
        substitute_test_document_urls(efile_data)

    assert efile_data["al_court_bundle"][0]["data_url"] == REAL_S3_URL


def test_substitution_is_inert_when_setting_is_absent_entirely(monkeypatch):
    """settings_prod/settings_staging never define the setting at all.

    Deleted rather than left to the ambient value: the suite runs under
    settings_dev, which defaults the stand-in URL to a real PDF so local fee
    quotes work, and `override_settings` cannot express "no such setting".
    """
    efile_data = _bundle()

    # Through the LazySettings wrapper, not settings._wrapped: __getattr__ caches
    # each setting on the wrapper, so deleting only from the inner object leaves
    # the cached value visible to getattr.
    monkeypatch.delattr(settings, "EFSP_TEST_DOCUMENT_URL", raising=False)
    substitute_test_document_urls(efile_data)

    assert efile_data["al_court_bundle"][0]["data_url"] == REAL_S3_URL


# --- EFSP_TEST_DOCUMENT_URL set outside development --------------------------
#
# Django's test environment forces DEBUG=False, so every "on" case below has to
# opt into DEBUG=True explicitly -- which is the precondition the substitution
# actually requires.


def test_stand_in_url_is_refused_when_debug_is_off():
    """A non-development process holding a stand-in URL must not file anything."""
    efile_data = _bundle()

    with override_settings(EFSP_TEST_DOCUMENT_URL=STAND_IN_URL, DEBUG=False):
        with pytest.raises(ImproperlyConfigured, match="DEBUG is False"):
            substitute_test_document_urls(efile_data)


def test_refusal_happens_before_any_url_is_rewritten():
    """The raise must not leave a half-substituted payload behind."""
    efile_data = {"al_court_bundle": [{"data_url": REAL_S3_URL}, {"data_url": REAL_S3_URL}]}

    with override_settings(EFSP_TEST_DOCUMENT_URL=STAND_IN_URL, DEBUG=False):
        with pytest.raises(ImproperlyConfigured):
            substitute_test_document_urls(efile_data)

    assert [b["data_url"] for b in efile_data["al_court_bundle"]] == [REAL_S3_URL, REAL_S3_URL]


def test_full_payload_preparation_refuses_too():
    """The guard holds on the path both the fee quote and the submission call."""
    efile_data = _bundle()

    with override_settings(EFSP_TEST_DOCUMENT_URL=STAND_IN_URL, DEBUG=False):
        with pytest.raises(ImproperlyConfigured):
            prepare_efile_payload(efile_data, "illinois", "adams")


# --- EFSP_TEST_DOCUMENT_URL on in development --------------------------------


def test_stand_in_url_replaces_every_document_url():
    efile_data = {
        "al_court_bundle": [
            {"data_url": REAL_S3_URL},
            {"data_url": "https://forms-mvp-xf6361.s3.us-east-1.amazonaws.com/efile-documents/supporting/d.pdf"},
        ]
    }

    with override_settings(EFSP_TEST_DOCUMENT_URL=STAND_IN_URL, DEBUG=True):
        substitute_test_document_urls(efile_data)

    assert [b["data_url"] for b in efile_data["al_court_bundle"]] == [STAND_IN_URL, STAND_IN_URL]


def test_substitution_warns_so_the_filing_is_not_mistaken_for_a_real_one(efile_logs):
    efile_data = _bundle()

    with override_settings(EFSP_TEST_DOCUMENT_URL=STAND_IN_URL, DEBUG=True):
        substitute_test_document_urls(efile_data)

    assert any("stand-in document" in record.getMessage() for record in efile_logs.records)


def test_substitution_leaves_other_bundle_fields_alone():
    efile_data = _bundle(filing_component="331", filing_type="27965")

    with override_settings(EFSP_TEST_DOCUMENT_URL=STAND_IN_URL, DEBUG=True):
        substitute_test_document_urls(efile_data)

    bundle = efile_data["al_court_bundle"][0]
    assert bundle["filing_component"] == "331"
    assert bundle["filing_type"] == "27965"


# --- cross_references --------------------------------------------------------


@pytest.mark.parametrize("empty_value", ["", None, [], {}])
def test_empty_cross_references_is_dropped_rather_than_sent(empty_value):
    efile_data = {"al_court_bundle": [], "cross_references": empty_value}

    with override_settings(EFSP_TEST_DOCUMENT_URL=""):
        prepare_efile_payload(efile_data, "illinois", "adams")

    assert "cross_references" not in efile_data


def test_populated_cross_references_is_preserved():
    efile_data = {"al_court_bundle": [], "cross_references": [{"code": "1", "value": "abc"}]}

    with override_settings(EFSP_TEST_DOCUMENT_URL=""):
        prepare_efile_payload(efile_data, "illinois", "adams")

    assert efile_data["cross_references"] == [{"code": "1", "value": "abc"}]


# --- placeholder filing components -------------------------------------------


class _ComponentsResponse:
    status_code = 200

    @staticmethod
    def json():
        return [{"code": "331", "name": "Lead Document"}, {"code": "332", "name": "Attachments"}]


def test_placeholder_component_label_is_resolved_to_the_court_code(monkeypatch, settings):
    monkeypatch.setattr("efile.services.efsp_payload.requests.get", lambda *args, **kwargs: _ComponentsResponse())
    settings.EFSP_URL = "https://efile-test.example"
    efile_data = _bundle(filing_component="supporting")

    resolve_placeholder_filing_components(efile_data, "illinois", "adams")

    assert efile_data["al_court_bundle"][0]["filing_component"] == "332"


def test_real_component_code_is_not_looked_up(monkeypatch, settings):
    def fail(*args, **kwargs):
        raise AssertionError("should not call the EFSP when the code is already real")

    monkeypatch.setattr("efile.services.efsp_payload.requests.get", fail)
    settings.EFSP_URL = "https://efile-test.example"
    efile_data = _bundle(filing_component="331")

    resolve_placeholder_filing_components(efile_data, "illinois", "adams")

    assert efile_data["al_court_bundle"][0]["filing_component"] == "331"


def test_repeated_filing_type_is_looked_up_once(monkeypatch, settings):
    calls = []

    def record(*args, **kwargs):
        calls.append(args)
        return _ComponentsResponse()

    monkeypatch.setattr("efile.services.efsp_payload.requests.get", record)
    settings.EFSP_URL = "https://efile-test.example"
    efile_data = {
        "al_court_bundle": [
            {"filing_type": "27965", "filing_component": "supporting"},
            {"filing_type": "27965", "filing_component": "attachment"},
        ]
    }

    resolve_placeholder_filing_components(efile_data, "illinois", "adams")

    assert len(calls) == 1
    assert [b["filing_component"] for b in efile_data["al_court_bundle"]] == ["332", "332"]


def test_unresolvable_component_is_left_for_the_efsp_to_reject(monkeypatch, settings):
    import requests

    def boom(*args, **kwargs):
        raise requests.RequestException("EFSP unreachable")

    monkeypatch.setattr("efile.services.efsp_payload.requests.get", boom)
    settings.EFSP_URL = "https://efile-test.example"
    efile_data = _bundle(filing_component="supporting")

    resolve_placeholder_filing_components(efile_data, "illinois", "adams")

    # Guessing a code would file under the wrong component; leave it visibly wrong.
    assert efile_data["al_court_bundle"][0]["filing_component"] == "supporting"
