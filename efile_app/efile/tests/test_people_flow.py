import re
from unittest.mock import patch

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.drafts import read_case_data
from efile.services.people import guess_filer_party_type
from efile.workflow import ExistingCase, WorkflowStepKey

PARTY_TYPES = [
    {"code": "plaintiff", "name": "Plaintiff", "required": True},
    {"code": "defendant", "name": "Defendant", "required": True},
]


def authorize(client, draft):
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session["jurisdiction"] = "illinois"
    session.save()


@pytest.fixture
def people_draft(client, django_user_model):
    user = django_user_model.objects.create_user(username="people-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        existing_case=ExistingCase.NEW,
        court_code="cook:cvd1",
        case_type_code="NC",
        case_type_name="Name Change",
        current_step=WorkflowStepKey.YOUR_INFORMATION,
    )
    client.force_login(user)
    authorize(client, draft)
    return draft


@pytest.mark.django_db
def test_your_information_persists_filer_contact(client, people_draft):
    response = client.post(
        reverse("your_information", kwargs={"jurisdiction": "illinois"}),
        {
            "first_name": "Jamie",
            "last_name": "Rivera",
            "address_line_1": "100 State Street",
            "city": "Chicago",
            "state": "IL",
            "zip_code": "60601",
            "email": "jamie@example.com",
            "phone": "312-555-0100",
        },
    )

    people_draft.refresh_from_db()
    filer = people_draft.parties.get(role="filer")
    assert response.status_code == 302
    assert response.url == reverse("parties", kwargs={"jurisdiction": "illinois"})
    assert filer.first_name == "Jamie"
    assert filer.address_line_1 == "100 State Street"
    assert people_draft.current_step == WorkflowStepKey.PARTIES


@pytest.mark.django_db
def test_your_information_suffix_is_a_dropdown_fed_by_the_court(client, people_draft):
    response = client.get(reverse("your_information", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    content = response.content.decode()
    suffix_select = re.search(r"<select[^>]*id=\"suffix\"[^>]*>", content)
    assert suffix_select is not None
    assert 'data-court="cook:cvd1"' in content


@pytest.mark.django_db
def test_your_information_returns_to_review_when_edited_from_there(client, people_draft):
    response = client.post(
        reverse("your_information", kwargs={"jurisdiction": "illinois"}),
        {
            "first_name": "Jamie",
            "last_name": "Rivera",
            "address_line_1": "100 State Street",
            "city": "Chicago",
            "state": "IL",
            "zip_code": "60601",
            "email": "jamie@example.com",
            "return_to": "review",
        },
    )

    people_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("case_review", kwargs={"jurisdiction": "illinois"})
    assert people_draft.current_step == WorkflowStepKey.REVIEW


@pytest.mark.django_db
def test_guess_filer_party_type_suggests_the_initiator_for_a_new_case(people_draft):
    guess = guess_filer_party_type(people_draft, PARTY_TYPES)

    assert guess == {"code": "plaintiff", "name": "Plaintiff", "required": True}


@pytest.mark.django_db
def test_guess_filer_party_type_suggests_the_respondent_for_an_answer(people_draft):
    people_draft.existing_case = ExistingCase.EXISTING
    people_draft.save(update_fields=["existing_case", "updated_at"])
    FilingDocument.objects.create(
        draft=people_draft,
        role=FilingDocument.Role.LEAD,
        name="answer.pdf",
        filing_type_name="Answer to Complaint",
    )

    guess = guess_filer_party_type(people_draft, PARTY_TYPES)

    assert guess == {"code": "defendant", "name": "Defendant", "required": True}


@pytest.mark.django_db
def test_guess_filer_party_type_is_none_without_a_clear_signal(people_draft):
    people_draft.existing_case = ExistingCase.EXISTING
    people_draft.save(update_fields=["existing_case", "updated_at"])

    assert guess_filer_party_type(people_draft, PARTY_TYPES) is None


@pytest.mark.django_db
def test_parties_page_offers_the_guess_as_a_button_not_a_prefill(client, people_draft):
    FilingParty.objects.create(draft=people_draft, role="filer", sort_order=0)

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        response = client.get(reverse("parties", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="apply-party-type-guess"' in content
    assert 'data-value="plaintiff"' in content
    plaintiff_radio = re.search(r'<input[^>]*name="filer_party_type"[^>]*value="plaintiff"[^>]*>', content)
    assert plaintiff_radio is not None
    assert "checked" not in plaintiff_radio.group()


@pytest.mark.django_db
def test_parties_page_hides_the_guess_once_a_role_is_chosen(client, people_draft):
    FilingParty.objects.create(draft=people_draft, role="filer", sort_order=0, party_type="defendant")

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        response = client.get(reverse("parties", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    assert b'id="apply-party-type-guess"' not in response.content


@pytest.mark.django_db
def test_parties_creates_missing_required_party_and_repeats_details(client, people_draft):
    filer = FilingParty.objects.create(
        draft=people_draft,
        role="filer",
        sort_order=0,
        first_name="Jamie",
        last_name="Rivera",
        address_line_1="100 State Street",
        city="Chicago",
        state="IL",
        zip_code="60601",
    )

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        response = client.post(
            reverse("parties", kwargs={"jurisdiction": "illinois"}),
            {"filer_party_type": "plaintiff"},
        )

    filer.refresh_from_db()
    other = people_draft.parties.get(role="other")
    assert response.status_code == 302
    assert response.url.endswith(f"?party={other.pk}")
    assert filer.party_type == "plaintiff"
    assert other.party_type == "defendant"
    assert other.party_type_name == "Defendant"


@pytest.mark.django_db
def test_parties_returns_to_review_when_edited_from_there(client, people_draft):
    FilingParty.objects.create(
        draft=people_draft,
        role="filer",
        sort_order=0,
        party_type="plaintiff",
        first_name="Jamie",
        last_name="Rivera",
        address_line_1="100 State Street",
        city="Chicago",
        state="IL",
        zip_code="60601",
    )
    FilingParty.objects.create(
        draft=people_draft,
        role="other",
        sort_order=0,
        party_type="defendant",
        party_type_name="Defendant",
        first_name="Morgan",
        last_name="Lee",
        address_line_1="200 Court Avenue",
        city="Chicago",
        state="IL",
        zip_code="60602",
    )

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        response = client.post(
            reverse("parties", kwargs={"jurisdiction": "illinois"}),
            {"filer_party_type": "plaintiff", "return_to": "review"},
        )

    people_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("case_review", kwargs={"jurisdiction": "illinois"})
    assert people_draft.current_step == WorkflowStepKey.REVIEW


@pytest.mark.django_db
def test_party_details_suffix_is_a_dropdown_fed_by_the_court(client, people_draft):
    party = FilingParty.objects.create(draft=people_draft, role="other", sort_order=0)

    with patch("efile.views.party_details.get_party_types", return_value=PARTY_TYPES):
        response = client.get(f"{reverse('party_details', kwargs={'jurisdiction': 'illinois'})}?party={party.pk}")

    assert response.status_code == 200
    content = response.content.decode()
    suffix_select = re.search(r"<select[^>]*id=\"suffix\"[^>]*>", content)
    assert suffix_select is not None
    assert 'data-court="cook:cvd1"' in content


@pytest.mark.django_db
def test_party_details_saves_party_and_advances_to_payment_when_no_questions(client, people_draft):
    FilingParty.objects.create(
        draft=people_draft,
        role="filer",
        sort_order=0,
        party_type="plaintiff",
        first_name="Jamie",
        last_name="Rivera",
        address_line_1="100 State Street",
        city="Chicago",
        state="IL",
        zip_code="60601",
    )
    party = FilingParty.objects.create(
        draft=people_draft,
        role="other",
        sort_order=0,
        party_type="defendant",
        party_type_name="Defendant",
    )

    with patch("efile.views.party_details.get_party_types", return_value=PARTY_TYPES):
        response = client.post(
            f"{reverse('party_details', kwargs={'jurisdiction': 'illinois'})}?party={party.pk}",
            {
                "party_kind": "person",
                "party_type": "defendant",
                "first_name": "Morgan",
                "last_name": "Lee",
                "address_line_1": "200 Court Avenue",
                "city": "Chicago",
                "state": "IL",
                "zip_code": "60602",
            },
        )

    people_draft.refresh_from_db()
    party.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("payment", kwargs={"jurisdiction": "illinois"})
    assert party.first_name == "Morgan"
    assert people_draft.current_step == WorkflowStepKey.PAYMENT


@pytest.mark.django_db
def test_party_details_returns_to_review_when_edited_from_there(client, people_draft):
    FilingParty.objects.create(
        draft=people_draft,
        role="filer",
        sort_order=0,
        party_type="plaintiff",
        first_name="Jamie",
        last_name="Rivera",
        address_line_1="100 State Street",
        city="Chicago",
        state="IL",
        zip_code="60601",
    )
    party = FilingParty.objects.create(
        draft=people_draft,
        role="other",
        sort_order=0,
        party_type="defendant",
        party_type_name="Defendant",
    )

    with patch("efile.views.party_details.get_party_types", return_value=PARTY_TYPES):
        response = client.post(
            f"{reverse('party_details', kwargs={'jurisdiction': 'illinois'})}?party={party.pk}",
            {
                "party_kind": "person",
                "party_type": "defendant",
                "first_name": "Morgan",
                "last_name": "Lee",
                "address_line_1": "200 Court Avenue",
                "city": "Chicago",
                "state": "IL",
                "zip_code": "60602",
                "return_to": "review",
            },
        )

    people_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("case_review", kwargs={"jurisdiction": "illinois"})
    assert people_draft.current_step == WorkflowStepKey.REVIEW


@pytest.mark.django_db
def test_case_questions_are_configured_and_saved(client, people_draft):
    people_draft.case_type_name = "Dissolution (with children)"
    people_draft.current_step = WorkflowStepKey.CASE_QUESTIONS
    people_draft.save(update_fields=["case_type_name", "current_step", "updated_at"])

    response = client.post(
        reverse("case_questions", kwargs={"jurisdiction": "illinois"}),
        {"has_children": "true", "child_count": "2"},
    )

    people_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("payment", kwargs={"jurisdiction": "illinois"})
    assert people_draft.supplemental_fields["has_children"] is True
    assert people_draft.supplemental_fields["child_count"] == 2
    assert people_draft.supplemental_fields["_case_questions_required"] is True


@pytest.mark.django_db
def test_case_questions_returns_to_review_when_edited_from_there(client, people_draft):
    people_draft.case_type_name = "Dissolution (with children)"
    people_draft.current_step = WorkflowStepKey.CASE_QUESTIONS
    people_draft.save(update_fields=["case_type_name", "current_step", "updated_at"])

    response = client.post(
        reverse("case_questions", kwargs={"jurisdiction": "illinois"}),
        {"has_children": "true", "child_count": "2", "return_to": "review"},
    )

    people_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("case_review", kwargs={"jurisdiction": "illinois"})
    assert people_draft.current_step == WorkflowStepKey.REVIEW


@pytest.mark.django_db
def test_new_parties_are_available_to_legacy_payload_bridge(people_draft):
    FilingParty.objects.create(
        draft=people_draft,
        role="filer",
        sort_order=0,
        party_type="plaintiff",
        party_type_name="Plaintiff",
        first_name="Jamie",
        last_name="Rivera",
        address_line_1="100 State Street",
        city="Chicago",
        state="IL",
        zip_code="60601",
    )

    data = read_case_data(people_draft)

    assert data["party_type"] == "plaintiff"
    assert data["petitioner_first_name"] == "Jamie"
    assert data["filing_parties"][0]["party_type_name"] == "Plaintiff"
