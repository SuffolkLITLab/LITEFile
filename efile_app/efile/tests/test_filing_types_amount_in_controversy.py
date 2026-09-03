"""The court's "amountincontroversy" flag on a filing type has to survive the
/api/dropdowns/filing-types/ round trip so organize_documents can tell whether
a chosen filing type requires an amount in controversy.
"""

import pytest
from django.urls import reverse

from efile.api.dropdown_views import DropdownAPIViews, prioritize_options
from efile.models import FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY


def test_prioritize_options_keeps_extra_fields_from_the_court():
    api_data = [
        {"code": "PET", "name": "Petition", "amountincontroversy": "Required", "fee": "50.00"},
        {"code": "ANS", "name": "Answer", "amountincontroversy": "NotApplicable"},
    ]

    options = prioritize_options(api_data, guessed=None)

    petition = next(opt for opt in options if opt["value"] == "PET")
    answer = next(opt for opt in options if opt["value"] == "ANS")
    assert petition["amountincontroversy"] == "Required"
    assert petition["fee"] == "50.00"
    assert answer["amountincontroversy"] == "NotApplicable"


def test_prioritize_options_marks_document_matches_with_an_asterisk():
    options = prioritize_options(
        [{"code": "PET", "name": "Petition"}, {"code": "ANS", "name": "Answer"}],
        guessed="Petition",
    )

    petition = next(opt for opt in options if opt["value"] == "PET")
    assert petition["text"] == "Petition *"
    assert "Recommended" not in petition["text"]


def test_guessed_court_uses_extraction_marker_without_location_recommendation():
    courts = [
        {"value": "cook:law1", "text": "Cook County Law Division"},
        {"value": "will:law1", "text": "Will County Law Division"},
    ]

    options = DropdownAPIViews._prioritize_courts_by_location(courts, guessed_court="Cook County")

    assert options[0]["text"] == "Cook County Law Division *"
    assert "Recommended" not in options[0]["text"]


class _FilingTypesResponse:
    status_code = 200
    headers = {"Content-Type": "application/json"}

    @staticmethod
    def json():
        return [
            {"code": "PET", "name": "Petition", "amountincontroversy": "Required"},
            {"code": "ANS", "name": "Answer", "amountincontroversy": "NotApplicable"},
        ]


@pytest.fixture
def draft_session(client, django_user_model):
    user = django_user_model.objects.create_user(username="amount-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()
    return draft


@pytest.mark.django_db
def test_filing_types_endpoint_surfaces_the_amount_in_controversy_flag(client, draft_session, monkeypatch):
    monkeypatch.setattr(
        "efile.api.dropdown_views.requests.get",
        lambda *args, **kwargs: _FilingTypesResponse(),
    )

    response = client.get(
        reverse("api:filing_types"),
        {"jurisdiction": "illinois", "court": "cook:cd1", "case_type": "200", "case_category": "100"},
    )

    assert response.status_code == 200
    body = response.json()
    petition = next(opt for opt in body["data"] if opt["value"] == "PET")
    assert petition["amountincontroversy"] == "Required"
