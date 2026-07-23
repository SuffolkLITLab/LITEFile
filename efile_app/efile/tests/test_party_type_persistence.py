"""The filer's own party type must survive the pages that guess at it.

`/api/get-party-types/` picks a likely party type from the case type's *name*
("civil" -> plaintiff) and stores it on the draft. It is a GET, called on page
load, including from the review page -- so before this was guarded it replaced a
filer who had chosen Defendant/Respondent with the guessed Plaintiff/Petitioner.
Both sides then held the same party type, and the court rejected the filing for a
required party that no longer had anyone in it.
"""

import pytest
from django.urls import reverse

from efile.models import FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.drafts import read_case_data, write_case_data

PLAINTIFF = {"code": "20646", "name": "Plaintiff/Petitioner", "isrequired": True}
DEFENDANT = {"code": "20641", "name": "Defendant/Respondent", "isrequired": True}


class _PartyTypesResponse:
    status_code = 200

    @staticmethod
    def json():
        return [PLAINTIFF, DEFENDANT]


@pytest.fixture
def draft_session(client, django_user_model):
    user = django_user_model.objects.create_user(username="party-type-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()
    return draft


def _fetch_party_types(client, monkeypatch):
    monkeypatch.setattr(
        "efile.api.suffolk_api_views.requests.get",
        lambda *args, **kwargs: _PartyTypesResponse(),
    )
    return client.get(
        reverse("api:get_party_types"),
        {"jurisdiction": "illinois", "court": "adams", "case_type": "76015", "existing_case": "no"},
    )


@pytest.mark.django_db
def test_a_chosen_party_type_is_not_replaced_by_the_guess(client, draft_session, monkeypatch):
    """The exact regression: self as Defendant, guess says Plaintiff."""
    write_case_data(draft_session, {"court": "adams", "case_type": "76015", "party_type": DEFENDANT["code"]})

    response = _fetch_party_types(client, monkeypatch)

    assert response.status_code == 200
    assert read_case_data(draft_session)["determined_party_type"] == DEFENDANT["code"]


@pytest.mark.django_db
def test_the_response_reports_the_stored_party_type_not_the_guess(client, draft_session, monkeypatch):
    """Otherwise the page shows one party type while the draft files another."""
    write_case_data(draft_session, {"court": "adams", "case_type": "76015", "party_type": DEFENDANT["code"]})

    response = _fetch_party_types(client, monkeypatch)

    assert response.json()["selected_party_type"] == DEFENDANT["code"]


@pytest.mark.django_db
def test_an_empty_draft_is_still_seeded_with_the_guess(client, draft_session, monkeypatch):
    """The guess remains a useful default -- it just stops being an override."""
    write_case_data(draft_session, {"court": "adams", "case_type": "76015"})

    response = _fetch_party_types(client, monkeypatch)

    assert response.json()["selected_party_type"] == PLAINTIFF["code"]
    assert read_case_data(draft_session)["determined_party_type"] == PLAINTIFF["code"]


@pytest.mark.django_db
def test_repeated_page_loads_do_not_drift(client, draft_session, monkeypatch):
    """Seed once, then hold: the review page reloading must not change the filing."""
    write_case_data(draft_session, {"court": "adams", "case_type": "76015"})

    _fetch_party_types(client, monkeypatch)
    write_case_data(draft_session, {"party_type": DEFENDANT["code"]})  # the filer corrects it
    _fetch_party_types(client, monkeypatch)
    _fetch_party_types(client, monkeypatch)

    assert read_case_data(draft_session)["determined_party_type"] == DEFENDANT["code"]
