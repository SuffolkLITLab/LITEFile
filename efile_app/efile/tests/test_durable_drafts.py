import json

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY, get_current_draft
from efile.services.drafts import (
    draft_snapshot,
    read_case_data,
    read_upload_data,
    write_case_data,
    write_upload_data,
)
from efile.workflow import WorkflowStepKey, get_workflow_step_choices


@pytest.mark.django_db
def test_write_case_data_normalizes_known_fields(django_user_model):
    user = django_user_model.objects.create_user(username="draft-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    case_data = {
        "court": "cook:cd",
        "court_name": "Cook County Circuit Court",
        "case_category": "MR",
        "case_type": "Name Change",
        "filing_type": "motion",
        "document_type": "petition",
        "selected_payment_account": "pay-123",
        "selected_payment_account_name": "Card ending in 4242",
        "optional_services": ["certified_copy"],
        "petitioner_first_name": "Ada",
        "petitioner_last_name": "Lovelace",
        "petitioner_email": "ada@example.com",
        "petitioner_party_type": "PET",
        "new_first_name": "Augusta Ada",
        "new_last_name": "Lovelace",
    }

    write_case_data(draft, case_data, current_step=WorkflowStepKey.CASE_INFORMATION)
    draft.refresh_from_db()

    assert draft.current_step == WorkflowStepKey.CASE_INFORMATION
    assert draft.court_code == "cook:cd"
    assert draft.case_category_code == "MR"
    assert draft.case_type_code == "Name Change"
    assert draft.filing_type_code == "motion"
    assert draft.document_type_code == "petition"
    assert draft.selected_payment_account_id == "pay-123"
    assert draft.optional_services == ["certified_copy"]

    petitioner = FilingParty.objects.get(draft=draft, role="petitioner")
    assert petitioner.first_name == "Ada"
    assert petitioner.last_name == "Lovelace"
    assert petitioner.email == "ada@example.com"
    assert petitioner.party_type == "PET"

    new_name = FilingParty.objects.get(draft=draft, role="new_name")
    assert new_name.first_name == "Augusta Ada"


@pytest.mark.django_db
def test_write_case_data_does_not_persist_unknown_keys(django_user_model):
    """Only modelled fields survive; there is no catch-all blob for random keys."""
    user = django_user_model.objects.create_user(username="typed-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")

    write_case_data(draft, {"court": "cook:cd", "totally_made_up_field": "should be dropped"})
    draft.refresh_from_db()

    assert draft.court_code == "cook:cd"
    assert "totally_made_up_field" not in read_case_data(draft)


@pytest.mark.django_db
def test_case_data_round_trips_through_the_model(django_user_model):
    user = django_user_model.objects.create_user(username="round-trip-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    case_data = {
        "court": "cook:cd",
        "case_category": "MR",
        "case_type": "Name Change",
        "filing_type": "motion",
        "document_type": "petition",
        "existing_case": "no",
        "petitioner_first_name": "Ada",
        "petitioner_party_type": "PET",
        "other_first_name": "Grace",
        "other_address_city": "Chicago",
    }

    write_case_data(draft, case_data)
    blob = read_case_data(draft)

    assert blob["court"] == "cook:cd"
    assert blob["case_type"] == "Name Change"
    assert blob["petitioner_first_name"] == "Ada"
    # petitioner party type is echoed under all three legacy aliases the browser reads
    assert blob["party_type"] == "PET"
    assert blob["determined_party_type"] == "PET"
    assert blob["other_first_name"] == "Grace"
    assert blob["other_address_city"] == "Chicago"


@pytest.mark.django_db
def test_write_upload_data_creates_lead_and_supporting_documents(django_user_model):
    user = django_user_model.objects.create_user(username="document-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    upload_data = {
        "files": {
            "lead": {
                "name": "petition.pdf",
                "url": "https://example.com/petition.pdf",
                "s3_key": "drafts/petition.pdf",
                "size": 1234,
                "type": "application/pdf",
            },
            "supporting": [
                {
                    "name": "order.pdf",
                    "url": "https://example.com/order.pdf",
                    "size": 4321,
                    "type": "application/pdf",
                }
            ],
        },
        "guesses": {"court": "Cook County"},
        "lead_filing_type": "efile",
        "lead_document_type": "petition",
        "lead_filing_component": "lead",
        "supporting_documents": [
            {
                "filing_type": "attachment",
                "document_type": "exhibit",
                "filing_component": "supporting",
                "cc_email": "copy@example.com",
            }
        ],
    }

    write_upload_data(draft, upload_data, current_step=WorkflowStepKey.DOCUMENTS)
    draft.refresh_from_db()

    assert draft.current_step == WorkflowStepKey.DOCUMENTS
    assert draft.extracted_guesses == {"court": "Cook County"}

    lead = FilingDocument.objects.get(draft=draft, role=FilingDocument.Role.LEAD)
    assert lead.name == "petition.pdf"
    assert lead.s3_key == "drafts/petition.pdf"
    assert lead.content_type == "application/pdf"
    assert lead.filing_type_code == "efile"

    supporting = FilingDocument.objects.get(draft=draft, role=FilingDocument.Role.SUPPORTING)
    assert supporting.name == "order.pdf"
    assert supporting.document_type_code == "exhibit"
    assert supporting.courtesy_copy_email == "copy@example.com"


@pytest.mark.django_db
def test_upload_data_round_trips_through_the_model(django_user_model):
    user = django_user_model.objects.create_user(username="upload-round-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    write_upload_data(
        draft,
        {
            "files": {"lead": {"name": "petition.pdf", "url": "https://example.com/petition.pdf"}},
            "lead_filing_type": "efile",
            "guesses": {"court": "Cook County"},
        },
    )

    blob = read_upload_data(draft)

    assert blob["files"]["lead"]["name"] == "petition.pdf"
    assert blob["files"]["lead"]["url"] == "https://example.com/petition.pdf"
    assert blob["lead_filing_type"] == "efile"
    assert blob["guesses"] == {"court": "Cook County"}


@pytest.mark.django_db
def test_supporting_documents_are_replaced_wholesale(django_user_model):
    user = django_user_model.objects.create_user(username="supporting-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    write_upload_data(draft, {"files": {"supporting": [{"name": "first.pdf"}, {"name": "second.pdf"}]}})
    assert draft.documents.filter(role=FilingDocument.Role.SUPPORTING).count() == 2

    write_upload_data(draft, {"files": {"supporting": [{"name": "only.pdf"}]}})

    supporting = draft.documents.filter(role=FilingDocument.Role.SUPPORTING)
    assert supporting.count() == 1
    assert supporting.first().name == "only.pdf"


@pytest.mark.django_db
def test_draft_snapshot_is_json_serializable(django_user_model):
    user = django_user_model.objects.create_user(username="snapshot-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois", court_code="cook:cd")

    snapshot = draft_snapshot(draft)

    assert snapshot is not None
    assert snapshot["id"] == draft.pk
    assert snapshot["court_code"] == "cook:cd"
    json.dumps(snapshot)


@pytest.mark.django_db
def test_create_draft_view_creates_durable_draft(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="testuser",
        password="testpass123",
        tyler_jurisdiction="illinois",
    )
    client.force_login(user)

    response = client.post(
        reverse("create_draft", kwargs={"jurisdiction": "illinois"}),
        data={},
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["redirect_url"] == reverse("upload_first", kwargs={"jurisdiction": "illinois"})

    draft = FilingDraft.objects.get(user=user)
    assert draft.jurisdiction == "illinois"
    assert draft.current_step == WorkflowStepKey.UPLOAD_FIRST
    assert payload["data"]["filing_draft"]["id"] == draft.pk


@pytest.mark.django_db
def test_current_draft_enforces_owner(client, django_user_model):
    illinois_user = django_user_model.objects.create_user(username="illinois-user", tyler_jurisdiction="illinois")
    other_user = django_user_model.objects.create_user(username="other-user", tyler_jurisdiction="massachusetts")
    other_draft = FilingDraft.objects.create(user=other_user, jurisdiction="illinois")
    expected_draft = FilingDraft.objects.create(user=illinois_user, jurisdiction="illinois")

    client.force_login(illinois_user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = other_draft.pk
    session.save()

    response = client.get(reverse("get_current_draft"))

    assert response.status_code == 200
    assert response.json()["data"]["filing_draft"]["id"] == expected_draft.pk


@pytest.mark.django_db
def test_current_draft_does_not_cross_jurisdictions(client, django_user_model):
    user = django_user_model.objects.create_user(username="multi-state-user", tyler_jurisdiction="illinois")
    illinois_draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    massachusetts_draft = FilingDraft.objects.create(user=user, jurisdiction="massachusetts")
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = massachusetts_draft.pk
    session.save()

    request = type("Request", (), {"user": user, "session": client.session})()
    current = get_current_draft(request, jurisdiction="illinois")

    assert current == illinois_draft


@pytest.mark.django_db
def test_save_case_endpoint_persists_into_current_draft(client, django_user_model):
    user = django_user_model.objects.create_user(username="endpoint-user", tyler_jurisdiction="illinois")
    client.force_login(user)
    client.post(
        reverse("create_draft", kwargs={"jurisdiction": "illinois"}),
        data={},
        content_type="application/json",
    )

    response = client.post(
        reverse("save_case_data_api"),
        data={
            "jurisdiction": "illinois",
            "data": {
                "existing_case": "no",
                "court": "cook:cd",
                "case_type": "Name Change",
                "petitioner_first_name": "Ada",
                "petitioner_last_name": "Lovelace",
            },
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    draft = FilingDraft.objects.get(user=user)
    assert draft.court_code == "cook:cd"
    assert draft.case_type_code == "Name Change"
    assert draft.parties.get(role="petitioner").first_name == "Ada"


@pytest.mark.django_db
def test_save_case_endpoint_requires_authentication(client):
    response = client.post(
        reverse("save_case_data_api"),
        data={"jurisdiction": "illinois", "data": {"court": "cook:cd"}},
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_model_step_choices_follow_workflow_registry():
    current_step = FilingDraft._meta.get_field("current_step")

    assert tuple(current_step.choices) == get_workflow_step_choices()


@pytest.mark.django_db
def test_partial_case_update_does_not_clear_omitted_fields(django_user_model):
    user = django_user_model.objects.create_user(username="partial-update-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        court_code="old-code",
        court_name="Court name to preserve",
    )

    write_case_data(draft, {"court": "new-code"})
    draft.refresh_from_db()

    assert draft.court_code == "new-code"
    assert draft.court_name == "Court name to preserve"
