"""Name suffix has to be one of the court's own codes, not free text."""

import pytest
from django.urls import reverse

from efile.models import FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY


class _NameSuffixesResponse:
    status_code = 200

    @staticmethod
    def json():
        return [{"name": "Jr.", "code": "JR"}, {"name": "Sr.", "code": "SR"}, {"name": "III", "code": "III"}]


@pytest.fixture
def draft_session(client, django_user_model):
    user = django_user_model.objects.create_user(username="suffix-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()
    return draft


@pytest.mark.django_db
def test_name_suffixes_proxies_the_courts_own_list(client, draft_session, monkeypatch):
    monkeypatch.setattr(
        "efile.api.dropdown_views.requests.get",
        lambda *args, **kwargs: _NameSuffixesResponse(),
    )

    response = client.get(reverse("api:name_suffixes"), {"jurisdiction": "illinois", "court": "cook:cd1"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert {"value": "JR", "text": "Jr."} in body["data"]


@pytest.mark.django_db
def test_name_suffixes_requires_a_court(client, draft_session):
    response = client.get(reverse("api:name_suffixes"), {"jurisdiction": "illinois"})

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert "court" in body["error"].lower()
