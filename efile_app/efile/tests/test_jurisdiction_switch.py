from unittest.mock import patch

import pytest
from django.urls import reverse

from efile.authentication import SuffolkEFileBackend
from efile.models import FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY


def _set_jurisdiction_session(client, jurisdiction, **extra):
    session = client.session
    session["auth_tokens"] = {f"TYLER-TOKEN-{jurisdiction.upper()}": f"{jurisdiction}-token"}
    session["jurisdiction"] = jurisdiction
    session.update(extra)
    session.save()


@pytest.fixture
def illinois_account(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="illinois:local-account",
        email="filer@example.com",
        tyler_username="filer@example.com",
        tyler_jurisdiction="illinois",
        first_name="Alex",
        last_name="Filer",
    )
    client.force_login(user)
    _set_jurisdiction_session(client, "illinois")
    return user


@pytest.mark.django_db
def test_profile_control_is_an_accessible_dropdown(client, illinois_account):
    response = client.get(reverse("efile_options", kwargs={"jurisdiction": "illinois"}))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-bs-toggle="dropdown"' in content
    assert 'aria-label="Open profile menu"' in content
    assert "Alex Filer" in content
    assert "filer@example.com" in content
    assert "File in a different state" in content
    assert "profileModal" not in content
    assert 'class="modal fade"' not in content


@pytest.mark.django_db
def test_changing_jurisdiction_clears_auth_and_active_filing_session(client, illinois_account):
    draft = FilingDraft.objects.create(user=illinois_account, jurisdiction="illinois")
    _set_jurisdiction_session(
        client,
        "illinois",
        **{
            CURRENT_DRAFT_SESSION_KEY: draft.pk,
            "case_data": {"court": "cook:law1"},
            "upload_data": {"files": {"lead": {"name": "petition.pdf"}}},
            "unrelated_stale_key": "must-not-cross-state-lines",
        },
    )

    response = client.post(reverse("change_jurisdiction", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 302
    assert response.url == reverse("efile_choose_jurisdiction")
    assert list(client.session.keys()) == []
    assert FilingDraft.objects.filter(pk=draft.pk, jurisdiction="illinois").exists()


@pytest.mark.django_db
def test_state_picker_requires_login_for_new_jurisdiction(client, illinois_account):
    response = client.get(reverse("jurisdiction_homepage", kwargs={"jurisdiction": "massachusetts"}))

    assert response.status_code == 302
    assert response.url == reverse("efile_login", kwargs={"jurisdiction": "massachusetts"})
    assert list(client.session.keys()) == []


@pytest.mark.django_db
def test_state_picker_reuses_only_matching_active_login(client, illinois_account):
    response = client.get(reverse("jurisdiction_homepage", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 302
    assert response.url == reverse("efile_options", kwargs={"jurisdiction": "illinois"})


@pytest.mark.django_db
def test_same_tyler_email_creates_separate_jurisdiction_accounts():
    backend = SuffolkEFileBackend()
    username = "same-filer@example.com"

    illinois_user = backend._get_or_create_user(
        username,
        {"tokens": {"TYLER-ID-ILLINOIS": "il-id", "TYLER-TOKEN-ILLINOIS": "il-token"}},
        "illinois",
    )
    massachusetts_user = backend._get_or_create_user(
        username,
        {
            "tokens": {
                "TYLER-ID-MASSACHUSETTS": "ma-id",
                "TYLER-TOKEN-MASSACHUSETTS": "ma-token",
            }
        },
        "massachusetts",
    )

    assert illinois_user.pk != massachusetts_user.pk
    assert illinois_user.tyler_jurisdiction == "illinois"
    assert massachusetts_user.tyler_jurisdiction == "massachusetts"
    assert illinois_user.tyler_username == massachusetts_user.tyler_username == username
    assert illinois_user.username != massachusetts_user.username


@pytest.mark.django_db
@patch("efile.authentication.auth_with_tyler_api")
def test_login_starts_a_clean_jurisdiction_session(mock_auth, client):
    mock_auth.return_value = {
        "tokens": {
            "TYLER-ID-MASSACHUSETTS": "ma-id",
            "TYLER-TOKEN-MASSACHUSETTS": "ma-token",
        }
    }
    session = client.session
    session["case_data"] = {"jurisdiction": "illinois"}
    session[CURRENT_DRAFT_SESSION_KEY] = 987
    session["jurisdiction"] = "illinois"
    session.save()

    response = client.post(
        reverse("efile_login", kwargs={"jurisdiction": "massachusetts"}),
        {"login_submit": "1", "email": "new-filer@example.com", "password": "secret-password"},
    )

    assert response.status_code == 302
    assert response.url == reverse("efile_options", kwargs={"jurisdiction": "massachusetts"})
    assert "case_data" not in client.session
    assert CURRENT_DRAFT_SESSION_KEY not in client.session
    assert client.session["jurisdiction"] == "massachusetts"
    assert client.session["auth_tokens"] == mock_auth.return_value["tokens"]
    assert client.session["user_email"] == "new-filer@example.com"
