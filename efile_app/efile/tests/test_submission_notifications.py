import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import RequestFactory
from django.urls import reverse

from efile.models import FilingDocument
from efile.services.submission_notifications import (
    PROXY_EMAIL_FIELDS,
    strip_client_email_fields,
    submission_email_fields,
)
from efile.utils.config_loader import config_loader

PUBLIC_ID = uuid.UUID("6b0f2a8e-6d0c-4f1e-9a51-0c2b9f3c1a7d")


def fake_draft(**values):
    """A submitted draft's notification inputs, with no uploaded documents."""
    defaults = {
        "pk": 12,
        "public_id": PUBLIC_ID,
        "court_code": "unknown",
        "selected_payment_account_type": "CC",
        "documents": FilingDocument.objects.none(),
    }
    return SimpleNamespace(**{**defaults, **values})


def test_notification_fields_are_disabled_by_default_for_each_state():
    request = RequestFactory().get("/")
    draft = fake_draft(selected_payment_account_type="WV", court_code="unknown")

    for jurisdiction in ("illinois", "massachusetts", "vermont"):
        config = config_loader.load_jurisdiction_config(jurisdiction)
        assert submission_email_fields(request, draft, jurisdiction, config) == {}


def test_plain_text_fallback_links_to_tracker_and_waiver_source():
    request = RequestFactory().get("/", HTTP_HOST="testserver")
    draft = fake_draft(selected_payment_account_type="WV", court_code="unknown")
    config = deepcopy(config_loader.load_jurisdiction_config("illinois"))
    config["submission_notifications"]["enabled"] = True
    config["submission_notifications"]["format"] = "plain_text"
    config["fee_waiver"]["source_url"] = "https://example.test/waiver"

    fields = submission_email_fields(request, draft, "illinois", config)
    tracker_url = request.build_absolute_uri(reverse("submission_tracker", kwargs={"public_id": PUBLIC_ID}))

    assert set(fields) == set(PROXY_EMAIL_FIELDS)
    assert tracker_url in fields["email_confirmation_contents"]
    assert "https://example.test/waiver" in fields["email_confirmation_contents"]
    assert "If you requested a fee waiver, check the court’s decision" in fields["email_confirmation_contents"]
    assert "Illinois Court Help" in fields["email_confirmation_contents"]
    assert "833-411-1121" in fields["email_confirmation_contents"]
    assert "\n" in fields["email_confirmation_contents"]
    assert all("<" not in value and ">" not in value for value in fields.values())
    assert fields["email_confirmation_contents"].count(tracker_url) == 1
    assert "accepted by the court" in fields["acceptance_contents"]
    assert "A filing in your submission" in fields["acceptance_contents"]
    neutral = fields["neutral_contents"]
    assert 'status|lower == "returned"' in neutral
    assert 'status|lower == "returned for changes"' in neutral
    assert 'status|lower == "returned to filer"' in neutral
    assert '"return" in status|lower' not in neutral


def test_waiver_note_is_omitted_when_no_waiver_was_selected():
    request = RequestFactory().get("/", HTTP_HOST="testserver")
    draft = fake_draft(selected_payment_account_type="CC", court_code="unknown")
    config = deepcopy(config_loader.load_jurisdiction_config("illinois"))
    config["submission_notifications"]["enabled"] = True
    config["fee_waiver"]["source_url"] = "https://example.test/waiver"

    fields = submission_email_fields(request, draft, "illinois", config)

    assert "waiver" not in fields["email_confirmation_contents"].lower()


def test_html_notifications_include_progress_and_escape_contact_markup():
    from bs4 import BeautifulSoup

    request = RequestFactory().get("/", HTTP_HOST="testserver")
    config = deepcopy(config_loader.load_jurisdiction_config("illinois"))
    config["submission_notifications"]["enabled"] = True
    with patch(
        "efile.services.submission_notifications.court_contact",
        return_value={"name": '<img src=x onerror="alert(1)"> {{name}} & help'},
    ):
        fields = submission_email_fields(request, fake_draft(), "illinois", config)
    for field, outcome in (
        ("email_confirmation_contents", "Received"),
        ("acceptance_contents", "Accepted"),
        ("rejected_contents", "Returned for changes"),
    ):
        assert fields[field].startswith("<!DOCTYPE html>")
        soup = BeautifulSoup(fields[field], "html.parser")
        assert not soup.find("img")
        assert '<img src=x onerror="alert(1)">' in soup.get_text()
        stages = soup.select('table[aria-label="Filing progress"] td')
        assert len(stages) == 4
        current = [stage for stage in stages if "Current" in stage.get_text()]
        assert len(current) == 1 and outcome in current[0].get_text()
        assert soup.find("a", href=f"http://testserver/submissions/{PUBLIC_ID}/")
    assert not fields["email_confirmation_subject"].startswith("<!DOCTYPE")


def test_email_timing_has_sourced_estimates_and_hours_without_invented_event_times():
    config = deepcopy(config_loader.load_jurisdiction_config("illinois"))
    config["submission_notifications"]["enabled"] = True
    fields = submission_email_fields(RequestFactory().get("/"), fake_draft(court_code="adams"), "illinois", config)
    body = fields["email_confirmation_contents"]
    assert "1–2 days" in body
    assert "8:15 a.m.–4:30 p.m." not in body
    assert "Courts are closed on Saturdays and Sundays." in body
    assert "Court hours" in body
    assert "Stage times appear when available" not in body
    assert "Typically" not in fields["acceptance_contents"]


def test_email_timing_cannot_introduce_html_or_proxy_template_expressions():
    config = deepcopy(config_loader.load_jurisdiction_config("illinois"))
    config["submission_notifications"]["enabled"] = True
    config["filing_timing"]["review"] = {
        "label": "{{name}} <script>alert(1)</script>",
        "source_url": 'https://example.test/{{status}}?q="test"',
    }
    fields = submission_email_fields(RequestFactory().get("/"), fake_draft(), "illinois", config)
    body = fields["email_confirmation_contents"]
    assert "{{name}}" not in body and "{{status}}" not in body
    assert "<script>" not in body
    assert "%7B%7Bname%7D%7D" in body and "&lt;script&gt;" in body
    assert "&quot;test&quot;" in body


def test_waiver_document_counts_as_a_waiver_request():
    request = RequestFactory().get("/", HTTP_HOST="testserver")
    config = deepcopy(config_loader.load_jurisdiction_config("illinois"))
    config["submission_notifications"]["enabled"] = True

    with patch("efile.services.submission_notifications.has_waiver_document", return_value=True):
        fields = submission_email_fields(request, fake_draft(), "illinois", config)

    assert "If you requested a fee waiver" in fields["email_confirmation_contents"]


def test_default_templates_are_available_for_another_enabled_jurisdiction():
    request = RequestFactory().get("/", HTTP_HOST="testserver")
    draft = fake_draft(selected_payment_account_type="CC", court_code="unknown")
    config = deepcopy(config_loader.load_jurisdiction_config("massachusetts"))
    config["submission_notifications"]["enabled"] = True

    fields = submission_email_fields(request, draft, "massachusetts", config)

    assert set(fields) == set(PROXY_EMAIL_FIELDS)
    assert "This is not court acceptance" in fields["email_confirmation_contents"]
    assert "mass.gov/orgs/court-service-centers" in fields["email_confirmation_contents"]


def test_client_cannot_supply_proxy_email_templates_or_change_other_data():
    filing = {field: "<script>browser copy</script>" for field in PROXY_EMAIL_FIELDS}
    filing["al_court_bundle"] = [{"filing_type": "123"}]
    filing["email"] = "lead@example.test"

    strip_client_email_fields(filing)

    assert not set(PROXY_EMAIL_FIELDS).intersection(filing)
    assert filing["al_court_bundle"] == [{"filing_type": "123"}]
    assert filing["email"] == "lead@example.test"


def test_notification_copy_escapes_template_injection_in_configured_values():
    request = RequestFactory().get("/", HTTP_HOST="testserver")
    draft = fake_draft(selected_payment_account_type="WV", court_code="unknown")
    config = deepcopy(config_loader.load_jurisdiction_config("illinois"))
    config["submission_notifications"]["enabled"] = True
    config["fee_waiver"]["source_url"] = "https://example.test/{{name}}"

    with patch("efile.services.submission_notifications.court_contact", return_value={"name": "{{name}}"}):
        fields = submission_email_fields(request, draft, "illinois", config)

    assert all("{{" not in value and "}}" not in value for value in fields.values())
    assert "%7B%7Bname%7D%7D" in fields["email_confirmation_contents"]


@pytest.mark.parametrize("enabled", [False, True])
def test_forwarded_payload_strips_client_templates_and_preserves_lead_contact(enabled):
    from efile.views import session_api

    request = RequestFactory().post("/", HTTP_HOST="testserver")
    request.session = SessionStore()
    request.session.update({"jurisdiction": "illinois", "auth_tokens": {}})
    draft = fake_draft(court_code="court-A", selected_payment_account_type="CC")
    efile_data = {
        "al_court_bundle": [],
        "users": [{"is_form_filler": True, "email": "filer@example.test"}],
        "lead_contact": {"name": {"first": "Filer"}, "email": "lead@example.test"},
        **{field: "client-controlled" for field in PROXY_EMAIL_FIELDS},
    }
    config = deepcopy(config_loader.load_jurisdiction_config("illinois"))
    config["submission_notifications"]["enabled"] = enabled
    api_response = SimpleNamespace(status_code=201, json=lambda: {"envelopeId": "env-1"})

    with (
        patch.object(session_api, "get_case_data", return_value={"court": "court-A"}),
        patch.object(session_api, "get_upload_data", return_value={"files": ["document"]}),
        patch.object(session_api, "outgoing_unavailable_message", return_value=""),
        patch.object(session_api, "prepare_efile_payload"),
        patch.object(session_api, "get_current_draft", return_value=draft),
        patch.object(session_api.config_loader, "load_jurisdiction_config", return_value=config),
        patch("requests.post", return_value=api_response) as post,
    ):
        result = session_api.forward_final_filing(request, {"efile_data": efile_data})

    sent = post.call_args.kwargs["json"]
    assert "lead_contact" in sent
    assert sent["lead_contact"]["email"] == "lead@example.test"
    assert sent["users"][0]["email"] == "filer@example.test"
    assert "email" not in sent
    if enabled:
        assert set(PROXY_EMAIL_FIELDS).issubset(sent)
        assert "client-controlled" not in str(sent)
    else:
        assert not set(PROXY_EMAIL_FIELDS).intersection(sent)
    assert result.status_code == 200


def test_notification_config_error_does_not_block_or_retry_filing():
    from efile.views import session_api

    request = RequestFactory().post("/", HTTP_HOST="testserver")
    request.session = SessionStore()
    request.session.update({"jurisdiction": "illinois", "auth_tokens": {}})
    draft = fake_draft(court_code="court-A", selected_payment_account_type="CC")
    efile_data = {"al_court_bundle": [], "lead_contact": {"email": "lead@example.test"}}
    api_response = SimpleNamespace(status_code=201, json=lambda: {"envelopeId": "env-1"})

    with (
        patch.object(session_api, "get_case_data", return_value={"court": "court-A"}),
        patch.object(session_api, "get_upload_data", return_value={"files": ["document"]}),
        patch.object(session_api, "outgoing_unavailable_message", return_value=""),
        patch.object(session_api, "prepare_efile_payload"),
        patch.object(session_api, "get_current_draft", return_value=draft),
        patch.object(session_api.config_loader, "load_jurisdiction_config", side_effect=ValueError("bad config")),
        patch("requests.post", return_value=api_response) as post,
    ):
        result = session_api.forward_final_filing(request, {"efile_data": efile_data})

    assert result.status_code == 200
    assert post.call_count == 1


def test_missing_optional_contacts_and_waiver_url_leave_no_empty_labels():
    config = deepcopy(config_loader.load_jurisdiction_config("massachusetts"))
    config["submission_notifications"]["enabled"] = True
    config.pop("fee_waiver", None)
    request = RequestFactory().get("/", HTTP_HOST="testserver")
    draft = fake_draft(selected_payment_account_type="WV", court_code="unknown")
    with patch("efile.services.submission_notifications.court_contact", return_value={}):
        fields = submission_email_fields(request, draft, "massachusetts", config)
    confirmation = fields["email_confirmation_contents"]
    assert "If you requested a fee waiver" in confirmation
    for empty_label in (
        "Website:",
        "Phone:",
        "Email:",
        "More information:",
        "For help,",
        "None",
        "$waiver_line",
        "$help_line",
    ):
        assert empty_label not in confirmation


def test_incomplete_template_configuration_falls_back_to_proxy_defaults():
    request = RequestFactory().get("/")
    config = {"submission_notifications": {"enabled": True, "templates": {"acceptance_subject": "Accepted"}}}
    assert submission_email_fields(request, fake_draft(), "illinois", config) == {}


def test_saved_callback_templates_do_not_repeat_submission_day_holiday_guidance():
    from efile.services.notification_email_html import render_notification_email

    timing = {
        "review": {
            "label": "1–2 days",
            "source_url": "https://court.example/timing",
            "closure_note": "Indigenous Peoples’ Day may add 1 day.",
        }
    }
    confirmation = render_notification_email("email_confirmation_contents", "Submitted", "https://example.test", timing)
    callback = render_notification_email("neutral_contents", "Updated", "https://example.test", timing)
    assert "Indigenous Peoples’ Day may add 1 day." in confirmation
    assert "Indigenous Peoples’ Day" not in callback
    assert timing["review"]["closure_note"]
