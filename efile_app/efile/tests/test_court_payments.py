"""Court restrictions are enforced against real account types at every boundary."""

import json
from unittest.mock import Mock, patch

import pytest
import requests
from django.urls import reverse

from efile.services.court_payments import bank_payment_policy, validate_filing_payment
from efile.services.fee_quotes import fee_inputs_token, record_fee_quote
from efile.tests import test_fee_quotes
from efile.tests.helpers import accepted_submission
from efile.tests.test_fee_quotes import efsp_fee_response

draft = test_fee_quotes.draft

ACCOUNTS = [
    {"paymentAccountID": "bank-1", "paymentAccountTypeCode": "BankAccount", "accountName": "Checking"},
    {"paymentAccountID": "pay-123", "paymentAccountTypeCode": "CC", "accountName": "Visa ending in 4242"},
    {"paymentAccountID": "wv-1", "paymentAccountTypeCode": "WV", "accountName": "Fee waiver"},
]


@pytest.fixture(autouse=True)
def payment_validation():
    """Keep the real validator; only external HTTP calls are replaced here."""


def response(payload, status=200):
    result = Mock(status_code=status, headers={"Content-Type": "application/json"}, text=json.dumps(payload))
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError()
    return result


@pytest.fixture
def proxy(monkeypatch):
    state = {"flag": "True", "accounts": ACCOUNTS, "lookups": [], "posts": []}

    def get(url, **kwargs):
        state["lookups"].append(url)
        if "/payments/payment-accounts/" in url:
            return response(state["accounts"])
        if url.endswith("/codes"):
            if state.get("outage"):
                raise requests.Timeout()
            return response({"restrictbankaccountpayment": state["flag"]})
        return response([])

    def post(url, **kwargs):
        state["posts"].append((url, kwargs.get("json")))
        return response(efsp_fee_response("12.00") if url.endswith("/fees") else {"filing_id": "SYNTHETIC-298"})

    monkeypatch.setattr("requests.get", get)
    monkeypatch.setattr("requests.post", post)
    return state


@pytest.mark.parametrize(
    "flag,expected",
    [
        (True, "restricted"),
        (False, "allowed"),
        ("True", "restricted"),
        ("False", "allowed"),
        (" false ", "allowed"),
        (None, "unknown"),
        ("", "unknown"),
        ("no", "unknown"),
        (0, "unknown"),
    ],
)
@pytest.mark.parametrize("jurisdiction", ["illinois", "massachusetts", "vermont"])
def test_location_flag_values(proxy, flag, expected, jurisdiction):
    proxy["flag"] = flag
    assert bank_payment_policy(jurisdiction, "court:one") == expected
    assert proxy["lookups"][-1].endswith(f"/{jurisdiction}/codes/courts/court%3Aone/codes")


@pytest.mark.parametrize("payload", [{}, [], None, "bad response"])
def test_missing_or_malformed_location_settings(payload):
    with patch("requests.get", return_value=response(payload)):
        assert bank_payment_policy("illinois", "court") == "unknown"


def test_http_error_and_invalid_json_are_unknown():
    with patch("requests.get", return_value=response({}, 503)):
        assert bank_payment_policy("illinois", "court") == "unknown"
    invalid = response({})
    invalid.json.side_effect = ValueError()
    with patch("requests.get", return_value=invalid):
        assert bank_payment_policy("illinois", "court") == "unknown"


@pytest.mark.parametrize("account_id", ["pay-123", "wv-1"])
def test_cards_and_waivers_do_not_depend_on_bank_settings(proxy, account_id):
    proxy["outage"] = True
    assert validate_filing_payment("vermont", "court", "token", account_id)["paymentAccountID"] == account_id
    assert not any(url.endswith("/codes") for url in proxy["lookups"])


@pytest.mark.django_db
@pytest.mark.parametrize("flag,bank_visible", [("False", True), ("True", False), (None, False)])
def test_account_choices_use_the_drafts_court(client, draft, proxy, flag, bank_visible):
    proxy["flag"] = flag
    body = client.get(reverse("api:payment_accounts") + f"?draft={draft.pk}").json()
    assert body["success"]
    assert ("bank-1" in [a["paymentAccountID"] for a in body["data"]]) == bank_visible
    assert {"pay-123", "wv-1"} <= {a["paymentAccountID"] for a in body["data"]}
    assert bool(body["bank_payment_message"]) != bank_visible


@pytest.mark.django_db
@pytest.mark.parametrize("outage", [False, True])
def test_forged_payment_form_cannot_save_a_bank_account(client, draft, proxy, outage):
    proxy["outage"] = outage
    url = reverse("payment", kwargs={"jurisdiction": "illinois"}) + f"?draft={draft.pk}"
    with patch("efile.views.payment.estimate_fees", return_value={}):
        result = client.post(url, {"selected_payment_account": "bank-1", "selected_payment_account_type": "CC"})
    assert result.status_code == 200
    assert b"bank payments" in result.content
    draft.refresh_from_db()
    assert draft.selected_payment_account_id == "pay-123"


@pytest.mark.django_db
def test_allowed_bank_can_be_saved(client, draft, proxy):
    proxy["flag"] = "False"
    result = client.post(
        reverse("payment", kwargs={"jurisdiction": "illinois"}), {"selected_payment_account": "bank-1"}
    )
    assert result.status_code == 302
    draft.refresh_from_db()
    assert (draft.selected_payment_account_id, draft.selected_payment_account_type) == ("bank-1", "BankAccount")


def fees(client, draft, account_id="bank-1"):
    return client.post(
        reverse("api:payment_fees"),
        {
            "efile_data": {"al_court_bundle": {}, "tyler_payment_id": "bank-1"},
            "payment_account_id": account_id,
            "fee_inputs_token": fee_inputs_token(draft),
        },
        content_type="application/json",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("flag", ["True", None])
def test_direct_quote_blocks_restricted_and_unknown_bank_policy(client, draft, proxy, flag):
    proxy["flag"] = flag
    result = fees(client, draft)
    assert result.status_code == 412
    assert result.json()["error_code"] == "payment_account_unavailable"
    assert result.json()["error_actions"][0]["url"].endswith(f"?draft={draft.pk}")
    assert proxy["posts"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("account_id", ["bank-1", "pay-123", "wv-1"])
def test_quote_uses_the_checked_account_not_the_payload_id(client, draft, proxy, account_id):
    proxy["flag"] = "False"
    with patch("efile.api.filing_views.prepare_efile_payload"):
        result = fees(client, draft, account_id)
    assert result.status_code == 200
    assert result.json()["quote_recorded"]
    assert proxy["posts"][0][1]["tyler_payment_id"] == account_id


@pytest.mark.django_db
@pytest.mark.parametrize("change", ["court", "policy", "outage", "account removed"])
def test_stale_bank_selection_cannot_submit_and_recovers_with_card(client, draft, proxy, change):
    draft.selected_payment_account_id = "bank-1"
    # Even a false saved type must not bypass the real account's restriction.
    draft.selected_payment_account_type = "CC"
    draft.save()
    if change == "court":
        draft.court_code = "another-court"
        draft.save()
    if change == "outage":
        proxy["outage"] = True
    if change == "account removed":
        proxy["accounts"] = ACCOUNTS[1:]
    record_fee_quote(draft, "12.00", [])
    payload = accepted_submission(draft, efile_data={"al_court_bundle": {}, "tyler_payment_id": "pay-123"})
    result = client.post(reverse("submit_final_filing"), payload, content_type="application/json")
    assert result.status_code == 412
    assert result.json()["error_code"] == "payment_account_unavailable"
    assert not proxy["posts"]
    draft.refresh_from_db()
    assert draft.status == "draft"

    draft.selected_payment_account_id = "pay-123"
    draft.save()
    record_fee_quote(draft, "12.00", [])
    payload = accepted_submission(draft, efile_data={"al_court_bundle": {}, "tyler_payment_id": "bank-1"})
    with patch("efile.views.session_api.prepare_efile_payload"):
        result = client.post(reverse("submit_final_filing"), payload, content_type="application/json")
    assert result.status_code == 200, result.content
    assert proxy["posts"][0][1]["tyler_payment_id"] == "pay-123"
    draft.refresh_from_db()
    assert draft.status == "submitted"


def test_failed_account_lookup_is_not_permission_to_pay(proxy):
    with patch("requests.get", side_effect=requests.Timeout()):
        with pytest.raises(ValueError, match="could not check"):
            validate_filing_payment("illinois", "court", "token", "bank-1")


def test_inactive_account_is_unavailable(proxy):
    proxy["accounts"] = [{**ACCOUNTS[0], "active": {"value": False}}]
    with pytest.raises(ValueError, match="no longer available"):
        validate_filing_payment("illinois", "court", "token", "bank-1")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("scenario", ["restricted", "unknown", "stale", "stale-submit"])
def test_bank_payment_browser_flow(live_server, client, django_user_model, tmp_path, proxy, scenario):
    import os
    import subprocess
    from pathlib import Path

    from django.conf import settings

    from efile.tests.test_document_extractions import authorize
    from efile.tests.test_payment_flow_browser import payment_ready_draft

    if not os.getenv("COURT_PAYMENT_BROWSER_TESTS"):
        pytest.skip("Opt-in: requires Chromium")
    user = django_user_model.objects.create_user(username=f"bank-{scenario}", tyler_jurisdiction="illinois")
    filing = payment_ready_draft(user, {})
    authorize(client, filing)
    proxy["flag"] = "False" if scenario.startswith("stale") else "True"
    original_get = requests.get
    original_post = requests.post
    recovery_signal = tmp_path / "court-available"

    def get(url, **kwargs):
        if scenario == "unknown" and url.endswith("/codes"):
            if not recovery_signal.exists():
                raise requests.Timeout()
            proxy["flag"] = "False"
        if scenario == "stale-submit" and url.endswith("/codes"):
            filing.refresh_from_db()
            if filing.current_step == "review":
                proxy["flag"] = "True"
        return original_get(url, **kwargs)

    def post(url, **kwargs):
        result = original_post(url, **kwargs)
        if scenario == "stale" and url.endswith("/fees"):
            proxy["flag"] = "True"
        return result

    evidence = Path(os.getenv("COURT_PAYMENT_EVIDENCE_DIR", str(tmp_path / "evidence")))
    config = tmp_path / "browser.json"
    config.write_text(
        json.dumps(
            {
                "baseUrl": live_server.url,
                "cookie": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "evidence": str(evidence),
                "paymentUrl": reverse("payment", kwargs={"jurisdiction": "illinois"}) + f"?draft={filing.pk}",
                "scenario": scenario,
                "recoverySignal": str(recovery_signal),
                "cookieName": settings.SESSION_COOKIE_NAME,
            }
        )
    )
    with (
        patch("requests.get", side_effect=get),
        patch("requests.post", side_effect=post),
        patch("efile.views.payment.estimate_fees", return_value={}),
        patch("efile.views.review.get_case_questions", return_value=[]),
    ):
        result = subprocess.run(
            ["node", "tests/court-payment-browser.js", str(config)],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
    print(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    filing.refresh_from_db()
    assert filing.status == "submitted"
    assert len([url for url, _ in proxy["posts"] if url.endswith("/filings")]) == 1
    assert proxy["posts"][-1][1]["tyler_payment_id"] == ("bank-1" if scenario == "unknown" else "pay-123")


@pytest.mark.django_db
def test_only_cards_need_no_location_lookup(client, draft, proxy):
    proxy["accounts"] = ACCOUNTS[1:]
    body = client.get(reverse("api:payment_accounts")).json()
    assert body["success"]
    assert "bank_payment_message" not in body
    assert not any(url.endswith("/codes") for url in proxy["lookups"])


@pytest.mark.django_db
def test_account_list_without_draft_stays_unfiltered(client, draft, proxy):
    from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY

    session = client.session
    session.pop(CURRENT_DRAFT_SESSION_KEY)
    session.save()
    body = client.get(reverse("api:payment_accounts")).json()
    assert body["data"] == ACCOUNTS
    assert not any(url.endswith("/codes") for url in proxy["lookups"])


@pytest.mark.django_db
def test_malformed_account_list_has_recovery_message(client, draft, proxy):
    proxy["accounts"] = {"error": "upstream failure"}
    result = client.get(reverse("api:payment_accounts"))
    assert result.status_code == 503
    assert "Please try again" in result.json()["error"]


def test_missing_token_asks_for_sign_in(proxy):
    with pytest.raises(ValueError, match="Sign in again"):
        validate_filing_payment("illinois", "court", None, "bank-1")
    assert not proxy["lookups"]


@pytest.mark.django_db
def test_payment_save_shows_only_the_actionable_error(client, draft, proxy):
    from django.contrib.messages import get_messages

    with patch("efile.views.payment.estimate_fees", return_value={}):
        result = client.post(
            reverse("payment", kwargs={"jurisdiction": "illinois"}), {"selected_payment_account": "bank-1"}
        )
    messages = [str(message) for message in get_messages(result.wsgi_request)]
    assert len(messages) == 1
    assert "does not accept bank payments" in messages[0]


@pytest.mark.django_db
def test_court_change_during_payment_check_blocks_submission(client, draft, proxy):
    from efile.models import FilingDraft

    record_fee_quote(draft, "12.00", [])
    original_get = requests.get

    def get(url, **kwargs):
        FilingDraft.objects.filter(pk=draft.pk).update(court_code="changed-court")
        return original_get(url, **kwargs)

    with patch("requests.get", side_effect=get):
        result = client.post(
            reverse("submit_final_filing"),
            accepted_submission(draft, efile_data={"al_court_bundle": {}}),
            content_type="application/json",
        )
    assert result.status_code == 412
    assert "changed while we checked" in result.json()["error"]
    assert not proxy["posts"]
    draft.refresh_from_db()
    assert draft.status == "draft"
