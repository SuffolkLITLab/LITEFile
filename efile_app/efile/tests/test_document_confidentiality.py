"""Jurisdiction defaults for the court's document confidentiality choices."""

import pytest
from django.urls import reverse

from efile.models import FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY


class _DocumentTypesResponse:
    status_code = 200

    @staticmethod
    def json():
        return [
            {"code": "PUBLIC", "name": "Non-confidential"},
            {"code": "SEALED", "name": "Confidential"},
        ]


@pytest.fixture
def draft_session(client, django_user_model):
    user = django_user_model.objects.create_user(username="confidentiality-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()
    return draft


@pytest.mark.django_db
def test_document_types_identify_non_confidential_choice(client, draft_session, monkeypatch):
    monkeypatch.setattr(
        "efile.api.dropdown_views.requests.get",
        lambda *args, **kwargs: _DocumentTypesResponse(),
    )

    response = client.get(
        reverse("api:document_types"),
        {"jurisdiction": "illinois", "court": "cook:cd1", "parent": "PET"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"value": "PUBLIC", "text": "No (Non-confidential)", "confidentiality": "non_confidential"},
        {"value": "SEALED", "text": "Yes (Confidential)", "confidentiality": "confidential"},
    ]
