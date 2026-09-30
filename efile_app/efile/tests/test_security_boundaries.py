"""Regression checks for public routes, configuration input, and filing logs."""

import logging
from unittest.mock import Mock, patch

import pytest
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import RequestFactory, override_settings

from efile.api.filing_views import get_tyler_token
from efile.views.session_api import forward_final_filing


@pytest.mark.parametrize("path", ["simple-s3-upload", "mock-s3-upload", "test-s3-connection", "debug-session"])
@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.django_db
def test_legacy_routes_are_unavailable_before_s3(client, path, debug):
    with override_settings(DEBUG=debug), patch("boto3.client") as s3:
        for method in (client.get, client.post):
            assert method(f"/api/{path}/").status_code == 404
    s3.assert_not_called()


@pytest.mark.parametrize("endpoint", ["case-type-config", "form-config", "filer-roles"])
@pytest.mark.django_db
def test_configuration_endpoints_reject_path_aliases(client, endpoint):
    response = client.get(f"/api/{endpoint}/", {"jurisdiction": "../states/illinois", "case_type": "name_change"})
    assert response.status_code == 400


@pytest.mark.parametrize("status", [201, 400, 500])
@override_settings(SUFFOLK_EFILE_API_KEY="secret-api-key-marker")
def test_submission_logs_exclude_secrets_and_contents(caplog, status):
    request = RequestFactory().post("/")
    request.session = SessionStore()
    request.session.update({"jurisdiction": "illinois", "auth_tokens": {"TYLER-TOKEN-ILLINOIS": "secret-token-marker"}})
    response = Mock(status_code=status, text="private-response-marker", headers={"secret": "secret-header-marker"})
    response.json.return_value = {"result": "private-response-marker"}
    with (
        caplog.at_level(logging.DEBUG, logger="efile.views.session_api"),
        patch.object(logging.getLogger("efile.views.session_api"), "handlers", [caplog.handler]),
        patch("efile.views.session_api.get_case_data", return_value={"court": "test-court"}),
        patch("efile.views.session_api.get_upload_data", return_value={"files": ["private-file-marker"]}),
        patch("efile.views.session_api.prepare_efile_payload"),
        patch("efile.views.session_api.describe_efsp_error", return_value="Upstream error"),
        patch("requests.post", return_value=response),
    ):
        result = forward_final_filing(request, {"efile_data": {"al_court_bundle": "private-payload-marker"}})
    assert result.status_code == (200 if status == 201 else status)
    assert "Filing submission response status=" in caplog.text
    for marker in (
        "secret-api-key-marker",
        "secret-token-marker",
        "secret-header-marker",
        "private-response-marker",
        "private-payload-marker",
        "private-file-marker",
    ):
        assert marker not in caplog.text


def test_token_lookup_does_not_log_session_credentials(caplog):
    request = RequestFactory().get("/")
    request.session = SessionStore()
    request.session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "secret-token-marker"}
    with (
        caplog.at_level(logging.DEBUG, logger="efile.api.filing_views"),
        patch.object(logging.getLogger("efile.api.filing_views"), "handlers", [caplog.handler]),
    ):
        assert get_tyler_token(request, "illinois") == "secret-token-marker"
    assert "secret-token-marker" not in caplog.text
