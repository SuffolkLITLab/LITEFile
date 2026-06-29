import json

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY, get_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.legacy_draft_bridge import sync_documents_from_upload_data, update_draft_from_case_data
from efile.workflow import WorkflowStepKey, get_workflow_step_choices


@pytest.mark.django_db
def test_update_draft_from_case_data_normalizes_known_fields(django_user_model):
    user = django_user_model.objects.create_user(username="draft-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
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

    update_draft_from_case_data(draft, case_data, current_step=WorkflowStepKey.CASE_INFORMATION)
    draft.refresh_from_db()

    assert draft.current_step == WorkflowStepKey.CASE_INFORMATION
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
def test_sync_documents_from_upload_data_creates_lead_and_supporting_documents(django_user_model):
    user = django_user_model.objects.create_user(username="document-owner", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
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

    sync_documents_from_upload_data(draft, upload_data, current_step=WorkflowStepKey.DOCUMENTS)
    draft.refresh_from_db()

    assert draft.current_step == WorkflowStepKey.DOCUMENTS
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
def test_legacy_case_endpoint_mirrors_into_current_draft(client, django_user_model):
    user = django_user_model.objects.create_user(username="bridge-user", tyler_jurisdiction="illinois")
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
def test_model_step_choices_follow_workflow_registry():
    current_step = FilingDraft._meta.get_field("current_step")

    assert tuple(current_step.choices) == get_workflow_step_choices()


@pytest.mark.django_db
def test_legacy_partial_case_update_does_not_clear_omitted_fields(django_user_model):
    user = django_user_model.objects.create_user(username="partial-update-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        court_code="old-code",
        court_name="Court name to preserve",
    )

    update_draft_from_case_data(draft, {"court": "new-code"})
    draft.refresh_from_db()

    assert draft.court_code == "new-code"
    assert draft.court_name == "Court name to preserve"


@pytest.mark.django_db
def test_legacy_upload_sync_removes_state_missing_from_complete_blob(django_user_model):
    user = django_user_model.objects.create_user(username="upload-replace-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        extracted_guesses={"court": "Old guess"},
    )
    FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.LEAD,
        name="old.pdf",
    )

    sync_documents_from_upload_data(draft, {"files": {}, "guesses": {}})
    draft.refresh_from_db()

    assert draft.extracted_guesses == {}
    assert not draft.documents.exists()
