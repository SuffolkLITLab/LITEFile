import uuid
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
from django.urls import reverse

from efile.models import FilingDraft

pytestmark = pytest.mark.django_db


@pytest.fixture
def draft(django_user_model):
    user = django_user_model.objects.create_user(
        username="owner", email="owner@example.com", tyler_jurisdiction="illinois"
    )
    return FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        court_code="cook:law1",
        status=FilingDraft.Status.SUBMITTED,
        submission_response={"filing_ids": ["accepted-id", "returned-id"]},
    )


def sign_in(client, user):
    client.force_login(user)
    session = client.session
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "test-token"}
    session.save()


def destination(draft):
    return reverse("submission_tracker", kwargs={"public_id": draft.public_id})


def test_signed_out_preserves_destination(client, draft):
    response = client.get(destination(draft) + "?filing_id=returned-id")
    assert response.status_code == 302
    login, query = response.url.split("?", 1)
    assert login == reverse("efile_login", args=["illinois"])
    assert parse_qs(query)["next"] == [destination(draft) + "?filing_id=returned-id"]


def test_signed_out_unknown_submission_is_not_found(client):
    response = client.get(reverse("submission_tracker", kwargs={"public_id": uuid.uuid4()}))
    assert response.status_code == 404


def test_submission_links_do_not_use_sequential_ids(client, draft):
    assert str(draft.pk) not in destination(draft).split("/")
    assert client.get(f"/submissions/{draft.pk}/").status_code == 404


def test_other_owner_cannot_open_submission(client, draft, django_user_model):
    sign_in(client, django_user_model.objects.create_user(username="other", tyler_jurisdiction="illinois"))
    assert client.get(destination(draft)).status_code == 404


def test_mixed_envelope_and_refresh_never_submit(client, draft):
    sign_in(client, draft.user)
    with patch("requests.post") as post:
        for _ in range(2):
            response = client.get(destination(draft))
            assert response.status_code == 200
            assert b"Choose a filing to check its status." in response.content
            assert b"accepted-id" in response.content and b"returned-id" in response.content
        post.assert_not_called()
    assert client.get(destination(draft) + "?filing_id=unowned").status_code == 404
    response = client.get(destination(draft) + "?filing_id=returned-id")
    assert response.url == reverse("filing_detail", args=["illinois", "cook:law1", "returned-id"])


def test_single_filing_and_envelope_only(client, draft):
    sign_in(client, draft.user)
    draft.submission_response = {"envelope_id": "envelope", "filing_id": "filing"}
    draft.save()
    assert client.get(destination(draft)).url == reverse("filing_detail", args=["illinois", "cook:law1", "filing"])
    draft.submission_response = {"envelope_id": "envelope"}
    draft.save()
    response = client.get(destination(draft))
    assert response.status_code == 200
    assert b"not available yet" in response.content


@pytest.mark.parametrize(
    "next_path",
    [
        "/submissions/6b0f2a8e-6d0c-4f1e-9a51-0c2b9f3c1a7d/?filing_id=returned-id",
        "https://evil.example/",
        "//evil.example/",
    ],
)
def test_login_preserves_only_safe_destination(client, draft, next_path):
    draft.user.backend = "django.contrib.auth.backends.ModelBackend"
    with patch("efile.views.login.authenticate", return_value=draft.user):
        response = client.post(
            reverse("efile_login", args=["illinois"]),
            {
                "login_submit": "1",
                "email": "owner@example.com",
                "password": "secret",
                "next": next_path,
            },
        )
    assert response.status_code == 302
    assert response.url == (next_path if next_path.startswith("/submissions/") else "/jurisdiction/illinois/options/")


def test_direct_detail_cannot_bypass_local_ownership(client, draft, django_user_model):
    other = django_user_model.objects.create_user(username="intruder", tyler_jurisdiction="illinois")
    sign_in(client, other)
    with patch("efile.views.my_cases.fetch_filing_detail") as fetch:
        response = client.get(reverse("filing_detail", args=["illinois", "cook:law1", "returned-id"]))
        assert response.status_code == 404
        fetch.assert_not_called()


def test_same_tyler_account_under_another_local_user_can_open_detail(client, draft, django_user_model):
    draft.user.tyler_username = "filer@example.com"
    draft.user.save()
    recreated = django_user_model.objects.create_user(
        username="recreated", tyler_jurisdiction="illinois", tyler_username="FILER@example.com"
    )
    sign_in(client, recreated)
    with (
        patch("efile.views.my_cases.fetch_filing_detail", return_value=None) as fetch,
        patch("efile.views.my_cases.court_names", return_value={}),
    ):
        response = client.get(reverse("filing_detail", args=["illinois", "cook:law1", "returned-id"]))
    assert response.status_code == 200
    fetch.assert_called_once()


def test_signed_in_to_another_jurisdiction_is_offered_the_right_sign_in(client, draft, django_user_model):
    elsewhere = django_user_model.objects.create_user(username="ma", tyler_jurisdiction="massachusetts")
    client.force_login(elsewhere)
    session = client.session
    session["auth_tokens"] = {"TYLER-TOKEN-MASSACHUSETTS": "test-token"}
    session.save()
    response = client.get(destination(draft))
    assert response.status_code == 302
    login, query = response.url.split("?", 1)
    assert login == reverse("efile_login", args=["illinois"])
    assert parse_qs(query)["next"] == [destination(draft)]


def test_same_tyler_account_under_another_local_user_can_open_tracker(client, draft, django_user_model):
    draft.user.tyler_user_id = "tyler-123"
    draft.user.save()
    recreated = django_user_model.objects.create_user(
        username="recreated", tyler_jurisdiction="illinois", tyler_user_id="tyler-123"
    )
    sign_in(client, recreated)
    response = client.get(destination(draft))
    assert response.status_code == 200
    assert b"accepted-id" in response.content


def test_pending_handoff_claim_wins_over_next(client, draft):
    draft.user.backend = "django.contrib.auth.backends.ModelBackend"
    session = client.session
    session["handoff_continue"] = "/handoff/claim/abc/"
    session.save()
    with patch("efile.views.login.authenticate", return_value=draft.user):
        response = client.post(
            reverse("efile_login", args=["illinois"]),
            {"login_submit": "1", "email": "owner@example.com", "password": "secret", "next": destination(draft)},
        )
    assert response.url == "/handoff/claim/abc/"
