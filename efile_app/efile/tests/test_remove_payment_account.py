from unittest.mock import Mock, patch

import pytest
from django.test import Client
from django.urls import reverse
from requests import HTTPError, Timeout

from efile.models import FilingDraft
from efile.services.payment_accounts import remove_payment_account

URL = reverse("api:delete_payment_account", args=["old-card"])
ACCOUNT = {"paymentAccountID": "old-card", "paymentAccountTypeCode": "CC"}


@pytest.fixture
def user(client, django_user_model):
    user = django_user_model.objects.create_user(username="remove-card", tyler_jurisdiction="illinois")
    client.force_login(user)
    session = client.session
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()
    return user


def test_service_removes_authenticated_account(settings):
    settings.EFSP_URL = "https://efsp.example"
    with (
        patch("efile.services.payment_accounts.payment_accounts", return_value=[ACCOUNT]),
        patch("efile.services.payment_accounts.requests.delete", return_value=Mock()) as delete,
    ):
        remove_payment_account("illinois", "token", "old-card")
    assert delete.call_args.args[0] == "https://efsp.example/jurisdictions/illinois/payments/payment-accounts/old-card"
    assert delete.call_args.kwargs["headers"]["tyler-token-illinois"] == "token"


@pytest.mark.parametrize("accounts", [[], [{**ACCOUNT, "paymentAccountTypeCode": "WV"}]])
def test_service_rejects_unlisted_accounts_and_waivers(accounts):
    with (
        patch("efile.services.payment_accounts.payment_accounts", return_value=accounts),
        patch("efile.services.payment_accounts.requests.delete") as delete,
        pytest.raises(ValueError),
    ):
        remove_payment_account("illinois", "token", "old-card")
    delete.assert_not_called()


@pytest.mark.django_db
def test_removal_clears_only_matching_editable_drafts(client, user):
    drafts = [
        FilingDraft.objects.create(
            user=user,
            jurisdiction=jurisdiction,
            status=status,
            selected_payment_account_id=account_id,
            quoted_fee_total="12.00",
            quoted_fee_fingerprint="old-quote",
            selected_payment_account_type="CC",
        )
        for jurisdiction, status, account_id in [
            ("illinois", "draft", "old-card"),
            ("illinois", "error", "old-card"),
            ("illinois", "submitted", "old-card"),
            ("vermont", "draft", "old-card"),
            ("illinois", "draft", "another-card"),
        ]
    ]
    with patch("efile.api.payment_views.remove_payment_account") as remove:
        response = client.delete(URL)
    assert response.status_code == 200
    remove.assert_called_once_with("illinois", "token", "old-card")
    for index, draft in enumerate(drafts):
        draft.refresh_from_db()
        assert draft.quoted_fee_total == ("" if index < 2 else "12.00")
        if index < 2:
            assert draft.selected_payment_account_id == ""
            assert draft.quoted_fee_fingerprint == ""


@pytest.mark.django_db
@pytest.mark.parametrize("error,status", [(Timeout(), 503), (HTTPError(), 503), (ValueError(), 400)])
def test_failed_removal_keeps_selection(client, user, error, status):
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois", selected_payment_account_id="old-card")
    with patch("efile.api.payment_views.remove_payment_account", side_effect=error):
        assert client.delete(URL).status_code == status
    draft.refresh_from_db()
    assert draft.selected_payment_account_id == "old-card"


@pytest.mark.django_db
def test_removal_requires_matching_login(client, user):
    with patch("efile.api.payment_views.remove_payment_account") as remove:
        assert client.delete(URL + "?jurisdiction=vermont").status_code == 401
        client.logout()
        assert client.delete(URL).status_code == 401
    remove.assert_not_called()


@pytest.mark.django_db
def test_removal_requires_csrf_and_delete(client, user):
    with patch("efile.api.payment_views.remove_payment_account") as remove:
        assert client.get(URL).status_code == 405
        assert client.post(URL).status_code == 405
        protected = Client(enforce_csrf_checks=True)
        protected.cookies = client.cookies
        assert protected.delete(URL).status_code == 403
    remove.assert_not_called()
