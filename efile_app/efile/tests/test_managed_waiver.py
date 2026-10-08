from unittest.mock import Mock, patch

import pytest
from django.test import Client
from django.urls import reverse
from requests import Timeout

from efile.services.payment_accounts import MANAGED_WAIVER_NAME, ensure_waiver_account
from efile.tests.test_review_submit_flow import submission_draft as _submission_draft

payment_draft = _submission_draft

pytestmark = pytest.mark.django_db


def response(data):
    result = Mock()
    result.json.return_value = data
    return result


@pytest.mark.parametrize("state", ["illinois", "massachusetts", "vermont"])
def test_create_only_when_no_active_waiver_exists(django_user_model, state):
    user = django_user_model.objects.create_user(username=state)
    existing = {"paymentAccountID": "old", "paymentAccountTypeCode": "WV", "active": False}
    with (
        patch("efile.services.payment_accounts.requests.get", return_value=response([existing])),
        patch("efile.services.payment_accounts.requests.post", return_value=response("new-waiver")) as post,
    ):
        result = ensure_waiver_account(user, state, "token")
    assert result["paymentAccountID"] == "new-waiver"
    assert post.call_args.kwargs["data"] == MANAGED_WAIVER_NAME
    assert post.call_args.kwargs["headers"][f"tyler-token-{state}"] == "token"
    assert "global" not in post.call_args.args[0]


@pytest.mark.parametrize("count", [1, 2])
def test_reuses_existing_waivers(django_user_model, count):
    user = django_user_model.objects.create_user(username="reuse")
    accounts = [{"paymentAccountID": str(i), "paymentAccountTypeCode": "WV"} for i in range(count)]
    with (
        patch("efile.services.payment_accounts.requests.get", return_value=response(accounts)),
        patch("efile.services.payment_accounts.requests.post") as post,
    ):
        assert ensure_waiver_account(user, "illinois", "token") == accounts[0]
    post.assert_not_called()


def test_keeps_the_filers_saved_waiver(django_user_model):
    user = django_user_model.objects.create_user(username="saved")
    accounts = [{"paymentAccountID": str(i), "paymentAccountTypeCode": "WV"} for i in range(2)]
    with patch("efile.services.payment_accounts.requests.get", return_value=response(accounts)):
        assert ensure_waiver_account(user, "illinois", "token", "1") == accounts[1]


def test_plain_text_account_id_is_not_a_failure(django_user_model):
    user = django_user_model.objects.create_user(username="plain")
    created = Mock(text="new-waiver\n")
    created.json.side_effect = ValueError
    with (
        patch("efile.services.payment_accounts.requests.get", return_value=response([])),
        patch("efile.services.payment_accounts.requests.post", return_value=created),
    ):
        assert ensure_waiver_account(user, "illinois", "token")["paymentAccountID"] == "new-waiver"


def test_deactivated_jaxb_waiver_is_not_reused(django_user_model):
    user = django_user_model.objects.create_user(username="jaxb")
    retired = {"paymentAccountID": "old", "paymentAccountTypeCode": "WV", "active": {"value": False, "nil": False}}
    with (
        patch("efile.services.payment_accounts.requests.get", return_value=response([retired])),
        patch("efile.services.payment_accounts.requests.post", return_value=response("new")),
    ):
        assert ensure_waiver_account(user, "illinois", "token")["paymentAccountID"] == "new"


def test_lookup_failure_never_creates_account(django_user_model):
    user = django_user_model.objects.create_user(username="failure")
    with (
        patch("efile.services.payment_accounts.requests.get", side_effect=Timeout),
        patch("efile.services.payment_accounts.requests.post") as post,
    ):
        with pytest.raises(Timeout):
            ensure_waiver_account(user, "illinois", "token")
    post.assert_not_called()


def test_waiver_endpoint_requires_authentication_and_csrf(client, payment_draft):
    url = reverse("api:waiver_account")
    assert Client().post(url).status_code == 401
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(payment_draft.user)
    assert csrf_client.post(url).status_code == 403
    assert client.get(url).status_code == 405


def test_waiver_endpoint_returns_account(client, payment_draft):
    with patch(
        "efile.api.payment_views.ensure_waiver_account",
        return_value={"paymentAccountID": "wv", "paymentAccountTypeCode": "WV"},
    ) as ensure:
        result = client.post(reverse("api:waiver_account"), {"preferred_id": "wv"}, content_type="application/json")
    assert result.json()["data"]["paymentAccountID"] == "wv"
    ensure.assert_called_once_with(payment_draft.user, "illinois", "test-token", "wv")


def test_post_cannot_disguise_a_card_as_a_waiver(client, payment_draft):
    with patch(
        "efile.views.payment.payment_accounts",
        return_value=[{"paymentAccountID": "card", "paymentAccountTypeCode": "CC", "accountName": "My card"}],
    ):
        result = client.post(
            reverse("payment", kwargs={"jurisdiction": "illinois"}),
            {"selected_payment_account": "card", "selected_payment_account_type": "WV"},
        )
    assert result.status_code == 302
    payment_draft.refresh_from_db()
    assert payment_draft.selected_payment_account_type == "CC"


def test_estimate_visible_before_payment_choice(client, payment_draft):
    with patch("efile.services.fee_estimates._codes", return_value=[{"code": "petition", "fee": "125"}]):
        result = client.get(reverse("payment", kwargs={"jurisdiction": "illinois"}))
    assert result.status_code == 200
    body = result.content.decode()
    assert "~$125.00" in body
    assert body.index("~$125.00") < body.index('name="paymentIntent"')
    payment_draft.refresh_from_db()
    assert payment_draft.quoted_fee_total == ""


@pytest.mark.parametrize("accounts", [[], [{"paymentAccountID": "someone-else", "paymentAccountTypeCode": "WV"}]])
def test_unknown_account_cannot_advance_to_review(client, payment_draft, accounts):
    with (
        patch("efile.views.payment.payment_accounts", return_value=accounts),
        patch("efile.services.fee_estimates._codes", return_value=[]),
    ):
        result = client.post(
            reverse("payment", kwargs={"jurisdiction": "illinois"}),
            {"selected_payment_account": "invented", "selected_payment_account_type": "WV"},
        )
    assert result.status_code == 200
    payment_draft.refresh_from_db()
    assert payment_draft.selected_payment_account_id == ""


def test_waiver_endpoint_reports_failure_without_redirect(client, payment_draft):
    with patch("efile.api.payment_views.ensure_waiver_account", side_effect=Timeout):
        result = client.post(reverse("api:waiver_account"))
    assert result.status_code == 503
    assert result.json()["success"] is False


def test_waiver_endpoint_rejects_other_jurisdiction(client, payment_draft):
    session = client.session
    session["auth_tokens"]["TYLER-TOKEN-VERMONT"] = "old-token"
    session.save()
    with patch("efile.api.payment_views.ensure_waiver_account") as ensure:
        result = client.post(reverse("api:waiver_account") + "?jurisdiction=vermont")
    assert result.status_code == 401
    ensure.assert_not_called()


def test_illinois_payment_displays_configured_poverty_range(client, payment_draft):
    with patch("efile.services.fee_estimates._codes", return_value=[]):
        result = client.get(reverse("payment", kwargs={"jurisdiction": "illinois"}))
    body = result.content.decode()
    accordion = body.split('<details class="fee-waiver-eligibility">')[1].split("</details>")[0]
    assert "125%–200%" in accordion
    assert "Up to" in accordion
    assert "partial reduction" in accordion
    assert "federal poverty level" in accordion


def test_statutory_exemption_choice_does_not_claim_low_income(client, payment_draft):
    from efile.services.fee_surcharges import matching_exemption
    from efile.utils.config_loader import config_loader

    payment_draft.case_type_name = "Relief from Abuse"
    policy = config_loader.load_jurisdiction_config("vermont")["fee_estimates"]["surcharges"]
    exemption = matching_exemption(policy, payment_draft)
    with patch("efile.views.payment.estimate_fees", return_value={"waiver_exemption": exemption}):
        result = client.get(reverse("payment", kwargs={"jurisdiction": "illinois"}))
    body = result.content.decode()
    assert "Claim the fee exemption for this case" in body
    assert "I think I qualify for a fee waiver" not in body
    assert "You do not need to qualify based on income" in body
    assert "Add fee waiver documents" not in body


def test_payment_without_a_fee_quote_can_open_review_for_corrections(client, payment_draft):
    assert payment_draft.quoted_fee_total == ""
    with patch(
        "efile.views.payment.payment_accounts",
        return_value=[{"paymentAccountID": "card", "paymentAccountTypeCode": "CC", "accountName": "My card"}],
    ):
        result = client.post(
            reverse("payment", kwargs={"jurisdiction": "illinois"}),
            {"selected_payment_account": "card"},
        )
    assert result.status_code == 302
    review = client.get(result.url)
    assert review.status_code == 200
    assert "return_to=review" in review.content.decode()
    payment_draft.refresh_from_db()
    assert payment_draft.selected_payment_account_id == "card"
    assert payment_draft.quoted_fee_total == ""
