from unittest.mock import patch

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
    return reverse("submission_tracker", kwargs={"submission_reference": draft.pk})


def test_signed_out_preserves_destination(client, draft):
    response = client.get(destination(draft) + "?filing_id=returned-id")
    assert response.status_code == 302
    assert "next=%2Fsubmissions%2F" in response.url
    assert "returned-id" in response.url


def test_other_owner_cannot_open_submission(client, draft, django_user_model):
    sign_in(client, django_user_model.objects.create_user(username="other", tyler_jurisdiction="illinois"))
    assert client.get(destination(draft)).status_code == 404


def test_mixed_envelope_and_refresh_never_submit(client, draft):
    sign_in(client, draft.user)
    with patch("requests.post") as post:
        for _ in range(2):
            response = client.get(destination(draft))
            assert response.status_code == 200
            assert b"Each filing can have a different outcome" in response.content
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
    "next_path", ["/submissions/1/?filing_id=returned-id", "https://evil.example/", "//evil.example/"]
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
