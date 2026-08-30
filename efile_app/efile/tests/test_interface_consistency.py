from unittest.mock import patch

import pytest
from django.urls import reverse
from pytest_django.asserts import assertTemplateUsed

JURISDICTION = "illinois"


@pytest.mark.django_db(False)
@pytest.mark.parametrize(
    "route_name",
    ["efile_login", "efile_register", "efile_password_reset"],
)
def test_account_screens_share_the_full_site_chrome(client, route_name):
    response = client.get(reverse(route_name, kwargs={"jurisdiction": JURISDICTION}))

    assert response.status_code == 200
    content = response.content.decode()
    assertTemplateUsed(response, "efile/auth_base.html")
    assert content.count('<header class="header">') == 1
    assert "profileMenuButton" in content
    assert "About LITEFile" in content
    assert "suffolk-lit-lab-logo.svg" in content
    assert "auth-shell" in content


@pytest.mark.django_db
@patch("efile.views.login.authenticate", return_value=None)
def test_login_error_stays_inline_and_cannot_be_dismissed(_authenticate, client):
    response = client.post(
        reverse("efile_login", kwargs={"jurisdiction": JURISDICTION}),
        {"login_submit": "1", "email": "filer@example.com", "password": "not-the-password"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "Login service error. Please try again later." in content
    assert "page-feedback__message--error" in content
    assert 'role="alert"' in content
    assert "alert-dismissible" not in content
    assert "btn-close" not in content


@pytest.mark.django_db
def test_registration_non_field_errors_are_rendered_inline(client):
    response = client.post(
        reverse("efile_register", kwargs={"jurisdiction": JURISDICTION}),
        {
            "first_name": "Taylor",
            "middle_name": "",
            "last_name": "Filer",
            "street_address": "1 Main Street",
            "street_address_2": "",
            "city": "Springfield",
            "state": "IL",
            "zip_code": "62701",
            "email": "taylor@example.com",
            "phone": "217-555-0100",
            "password": "valid-password-1",
            "confirm_password": "different-password-2",
        },
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "Passwords don&#x27;t match" in content
    assert 'aria-label="Form errors"' in content
    assert "page-feedback__message--error" in content
