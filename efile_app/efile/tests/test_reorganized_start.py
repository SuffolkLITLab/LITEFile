from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.workflow import ExistingCase, WorkflowStepKey


def authorize(client, draft):
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session["jurisdiction"] = "illinois"
    session.save()


@pytest.fixture
def reorganized_draft(client, django_user_model):
    user = django_user_model.objects.create_user(username="flow-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois", workflow_version=2)
    client.force_login(user)
    authorize(client, draft)
    return draft


@pytest.mark.django_db
def test_filing_path_saves_normalized_branch(client, reorganized_draft):
    response = client.post(
        reverse("filing_path", kwargs={"jurisdiction": "illinois"}),
        {"existing_case": ExistingCase.EXISTING},
    )

    reorganized_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("upload_documents", kwargs={"jurisdiction": "illinois"})
    assert reorganized_draft.existing_case == ExistingCase.EXISTING
    assert reorganized_draft.current_step == WorkflowStepKey.UPLOAD_DOCUMENTS


@pytest.mark.django_db
def test_upload_documents_persists_lead_supporting_and_guesses(client, reorganized_draft):
    handler = MagicMock()
    handler._ensure_initialized.return_value = True
    handler.validate_file.return_value = {"valid": True}
    handler.upload_file.side_effect = [
        {"success": True, "key": "lead.pdf"},
        {"success": True, "key": "supporting.pdf"},
    ]
    handler.get_public_url.side_effect = ["https://example.com/lead.pdf", "https://example.com/supporting.pdf"]
    lead = SimpleUploadedFile("petition.pdf", b"%PDF lead", content_type="application/pdf")
    supporting = SimpleUploadedFile("exhibit.pdf", b"%PDF exhibit", content_type="application/pdf")

    with (
        patch("efile.services.document_uploads.S3UploadHandler", return_value=handler),
        patch(
            "efile.services.document_uploads._analyze_lead",
            return_value={"court name": "Cook County", "case type": "Name Change"},
        ),
    ):
        response = client.post(
            reverse("upload_documents", kwargs={"jurisdiction": "illinois"}),
            {"documents": [lead, supporting]},
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    reorganized_draft.refresh_from_db()
    assert reorganized_draft.extracted_guesses["court"] == "Cook County"
    assert reorganized_draft.documents.get(role=FilingDocument.Role.LEAD).name == "petition.pdf"
    assert reorganized_draft.documents.get(role=FilingDocument.Role.SUPPORTING).name == "exhibit.pdf"


@pytest.mark.django_db
def test_removing_analyzed_document_cleans_storage_and_stale_guesses(client, reorganized_draft):
    lead = FilingDocument.objects.create(
        draft=reorganized_draft,
        role=FilingDocument.Role.LEAD,
        sort_order=0,
        name="petition.pdf",
        s3_key="lead/petition.pdf",
    )
    supporting = FilingDocument.objects.create(
        draft=reorganized_draft,
        role=FilingDocument.Role.SUPPORTING,
        sort_order=0,
        name="exhibit.pdf",
    )
    reorganized_draft.extracted_guesses = {"court": "Cook County"}
    reorganized_draft.save(update_fields=["extracted_guesses", "updated_at"])
    handler = MagicMock()
    handler._ensure_initialized.return_value = True
    handler.delete_file.return_value = {"success": True}

    with patch("efile.views.upload_documents.S3UploadHandler", return_value=handler):
        response = client.post(
            reverse("upload_documents", kwargs={"jurisdiction": "illinois"}),
            {"action": "remove", "document_id": lead.pk},
        )

    reorganized_draft.refresh_from_db()
    supporting.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["success"] is True
    handler.delete_file.assert_called_once_with("lead/petition.pdf")
    assert reorganized_draft.extracted_guesses == {}
    assert supporting.role == FilingDocument.Role.LEAD


@pytest.mark.django_db
def test_extraction_review_branches_new_case_to_checklist(client, reorganized_draft):
    FilingDocument.objects.create(
        draft=reorganized_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
    )

    response = client.post(
        reverse("extraction_review", kwargs={"jurisdiction": "illinois"}),
        {
            "existing_case": ExistingCase.NEW,
            "court_code": "cook",
            "court_name": "Cook County Circuit Court",
            "case_category_code": "MR",
            "case_category_name": "Miscellaneous Remedy",
            "case_type_code": "NC",
            "case_type_name": "Name Change",
        },
    )

    reorganized_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("document_checklist", kwargs={"jurisdiction": "illinois"})
    assert reorganized_draft.existing_case == ExistingCase.NEW
    assert reorganized_draft.court_code == "cook"
    assert reorganized_draft.case_type_code == "NC"
    assert reorganized_draft.case_type_name == "Name Change"
    assert reorganized_draft.current_step == WorkflowStepKey.DOCUMENT_CHECKLIST


@pytest.mark.django_db
def test_extraction_review_returns_to_review_when_edited_from_there(client, reorganized_draft):
    FilingDocument.objects.create(
        draft=reorganized_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
    )

    response = client.post(
        reverse("extraction_review", kwargs={"jurisdiction": "illinois"}),
        {
            "existing_case": ExistingCase.NEW,
            "court_code": "cook",
            "court_name": "Cook County Circuit Court",
            "case_category_code": "MR",
            "case_category_name": "Miscellaneous Remedy",
            "case_type_code": "NC",
            "case_type_name": "Name Change",
            "return_to": "review",
        },
    )

    reorganized_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("case_review", kwargs={"jurisdiction": "illinois"})
    assert reorganized_draft.current_step == WorkflowStepKey.REVIEW


@pytest.mark.django_db
def test_extraction_review_new_case_requires_matched_court_and_type(client, reorganized_draft):
    FilingDocument.objects.create(
        draft=reorganized_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
    )

    response = client.post(
        reverse("extraction_review", kwargs={"jurisdiction": "illinois"}),
        {
            "existing_case": ExistingCase.NEW,
            "court_name": "Cook County Circuit Court",
            "case_category_name": "Miscellaneous Remedy",
            "case_type_name": "Name Change",
        },
    )

    reorganized_draft.refresh_from_db()
    assert response.status_code == 200
    assert b"Choose a court, case category, and case type" in response.content
    assert reorganized_draft.current_step == WorkflowStepKey.EXTRACTION_REVIEW
    assert reorganized_draft.court_code == ""


@pytest.mark.django_db
def test_extraction_review_requires_a_case_path(client, reorganized_draft):
    FilingDocument.objects.create(
        draft=reorganized_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
    )

    response = client.post(
        reverse("extraction_review", kwargs={"jurisdiction": "illinois"}),
        {"existing_case": ExistingCase.UNSURE},
    )

    assert response.status_code == 200
    assert b"Choose whether this is a new or existing court case" in response.content
