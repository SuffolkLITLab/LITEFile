import json

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.services.drafts import draft_snapshot, sync_documents_from_upload_data, update_draft_from_case_data


@pytest.mark.django_db
def test_update_draft_from_case_data_normalizes_known_fields():
    draft = FilingDraft.objects.create(jurisdiction="illinois")
    case_data = {
        "court": "cook:cd",
        "court_name": "Cook County Circuit Court",
        "case_category": "MR",
        "case_category_name": "Miscellaneous Remedy",
        "case_type": "Name Change",
        "case_type_name": "Change of Name",
        "filing_type": "motion",
        "filing_type_name": "Motion",
        "document_type": "petition",
        "document_type_name": "Petition",
        "selected_payment_account": "pay-123",
        "selected_payment_account_name": "Card ending in 4242",
        "optional_services": ["certified_copy"],
        "petitioner_first_name": "Ada",
        "petitioner_last_name": "Lovelace",
        "petitioner_email": "ada@example.com",
        "new_first_name": "Augusta Ada",
        "new_last_name": "Lovelace",
    }

    update_draft_from_case_data(draft, case_data, current_step=FilingDraft.WorkflowStep.CASE_INFORMATION)
    draft.refresh_from_db()

    assert draft.current_step == FilingDraft.WorkflowStep.CASE_INFORMATION
    assert draft.court_code == "cook:cd"
    assert draft.case_category_code == "MR"
    assert draft.case_type_code == "Name Change"
    assert draft.filing_type_code == "motion"
    assert draft.document_type_code == "petition"
    assert draft.selected_payment_account_id == "pay-123"
    assert draft.optional_services == ["certified_copy"]
    assert draft.extra_case_data["petitioner_first_name"] == "Ada"

    petitioner = FilingParty.objects.get(draft=draft, role="petitioner")
    assert petitioner.first_name == "Ada"
    assert petitioner.last_name == "Lovelace"
    assert petitioner.email == "ada@example.com"

    name_sought = FilingParty.objects.get(draft=draft, role="name_sought")
    assert name_sought.first_name == "Augusta Ada"


@pytest.mark.django_db
def test_sync_documents_from_upload_data_creates_lead_and_supporting_documents():
    draft = FilingDraft.objects.create(jurisdiction="illinois")
    upload_data = {
        "files": {
            "lead": {
                "name": "petition.pdf",
                "url": "https://example.com/petition.pdf",
                "s3_key": "drafts/petition.pdf",
                "size": 1234,
                "content_type": "application/pdf",
            },
            "supporting": [
                {
                    "name": "order.pdf",
                    "url": "https://example.com/order.pdf",
                    "size": 4321,
                    "content_type": "application/pdf",
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

    sync_documents_from_upload_data(draft, upload_data, current_step=FilingDraft.WorkflowStep.DOCUMENTS)
    draft.refresh_from_db()

    assert draft.current_step == FilingDraft.WorkflowStep.DOCUMENTS
    assert draft.extracted_guesses == {"court": "Cook County"}

    lead = FilingDocument.objects.get(draft=draft, role=FilingDocument.Role.LEAD)
    assert lead.name == "petition.pdf"
    assert lead.s3_key == "drafts/petition.pdf"
    assert lead.filing_type_code == "efile"

    supporting = FilingDocument.objects.get(draft=draft, role=FilingDocument.Role.SUPPORTING)
    assert supporting.name == "order.pdf"
    assert supporting.document_type_code == "exhibit"
    assert supporting.courtesy_copy_email == "copy@example.com"


@pytest.mark.django_db
def test_draft_snapshot_is_json_serializable():
    draft = FilingDraft.objects.create(jurisdiction="illinois", court_code="cook:cd")

    snapshot = draft_snapshot(draft)

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
    assert draft.current_step == FilingDraft.WorkflowStep.UPLOAD_FIRST
    assert payload["data"]["filing_draft"]["id"] == draft.pk
