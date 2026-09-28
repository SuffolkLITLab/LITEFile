"""Telling a filer why they cannot sign in, when anyone can tell."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from django.urls import reverse

from efile.models import PendingActivation
from efile.utils.proxy_connection import EfspUnavailable, auth_with_tyler_api

LOGIN_URL = reverse("efile_login", kwargs={"jurisdiction": "illinois"})
REGISTER_URL = reverse("efile_register", kwargs={"jurisdiction": "illinois"})


def sign_in(client, email="new.filer@example.com"):
    return client.post(
        LOGIN_URL, {"login_submit": "1", "email": email, "password": "Correct-Horse-1!"}, follow=True
    ).content.decode()


def registration_form(**overrides):
    return {
        "first_name": "New",
        "last_name": "Filer",
        "street_address": "100 Main St",
        "city": "Chicago",
        "state": "IL",
        "zip_code": "60601",
        "email": "New.Filer@example.com",
        "phone": "312-555-0100",
        "password": "Correct-Horse-1!",
        "confirm_password": "Correct-Horse-1!",
        **overrides,
    }


def efsp_response(status, body=None):
    response = MagicMock(status_code=status, headers={"Content-Type": "application/json"}, text="")
    response.json.return_value = body or {}
    return response


# -- The proxy call ---------------------------------------------------------


def test_a_refused_sign_in_is_none_and_an_outage_raises():
    with patch("efile.utils.proxy_connection.requests.post", return_value=efsp_response(403)):
        assert auth_with_tyler_api("a@example.com", "pw", "illinois") is None
    with patch("efile.utils.proxy_connection.requests.post", return_value=efsp_response(502)):
        with pytest.raises(EfspUnavailable):
            auth_with_tyler_api("a@example.com", "pw", "illinois")
    with patch("efile.utils.proxy_connection.requests.post", side_effect=requests.ConnectionError("down")):
        with pytest.raises(EfspUnavailable):
            auth_with_tyler_api("a@example.com", "pw", "illinois")


# -- Registration -----------------------------------------------------------


@pytest.mark.django_db
def test_registering_remembers_the_account_needs_activation_and_lands_on_sign_in(client):
    created = efsp_response(201, {"userID": "u-1", "activationRequired": True})
    with patch("efile.views.register.requests.post", return_value=created) as post:
        response = client.post(REGISTER_URL, registration_form())

    assert response.status_code == 302
    assert response.url == LOGIN_URL
    # Once: a second POST would try to register the same email twice.
    assert post.call_count == 1
    assert PendingActivation.exists_for("new.filer@example.com", "illinois")
    page = client.get(response.url).content.decode()
    assert "select the activation link" in page
    assert "New.Filer@example.com" in page


@pytest.mark.django_db
def test_registration_never_logs_the_password(client, caplog):
    caplog.set_level("DEBUG")
    with patch("efile.views.register.requests.post", return_value=efsp_response(201, {})):
        client.post(REGISTER_URL, registration_form())

    assert "Correct-Horse-1!" not in caplog.text


# -- Signing in -------------------------------------------------------------


@pytest.mark.django_db
@patch("efile.authentication.auth_with_tyler_api", return_value=None)
def test_an_unactivated_account_is_told_to_activate(_auth, client):
    PendingActivation.remember("new.filer@example.com", "illinois")

    page = sign_in(client, email="NEW.filer@example.com")

    assert "Your account is not activated yet" in page
    assert "NEW.filer@example.com" in page
    assert "spam or junk folder" in page
    assert "Login service error" not in page


@pytest.mark.django_db
@patch("efile.authentication.auth_with_tyler_api", return_value=None)
def test_activation_is_only_mentioned_for_the_jurisdiction_it_was_registered_in(_auth, client):
    PendingActivation.remember("new.filer@example.com", "vermont")

    page = sign_in(client)

    assert "not activated yet" not in page
    assert "did not match an account" in page


@pytest.mark.django_db
@patch("efile.authentication.auth_with_tyler_api", return_value=None)
def test_a_refused_sign_in_is_not_called_a_service_error(_auth, client):
    page = sign_in(client, email="someone@example.com")

    assert "did not match an account" in page
    assert "If you just registered, activate your account" in page
    assert "Login service error" not in page


@pytest.mark.django_db
@patch("efile.authentication.auth_with_tyler_api", side_effect=EfspUnavailable("down"))
def test_an_outage_says_so_instead_of_blaming_the_password(_auth, client):
    PendingActivation.remember("new.filer@example.com", "illinois")

    page = sign_in(client)

    assert "could not reach the court" in page
    assert "did not match" not in page
    assert "not activated" not in page


@pytest.mark.django_db
@patch(
    "efile.authentication.auth_with_tyler_api",
    return_value={"tokens": {"TYLER-TOKEN-ILLINOIS": "t", "TYLER-ID-ILLINOIS": "id"}},
)
def test_signing_in_once_activated_forgets_the_pending_activation(_auth, client):
    PendingActivation.remember("new.filer@example.com", "illinois")

    sign_in(client)

    assert not PendingActivation.exists_for("new.filer@example.com", "illinois")
