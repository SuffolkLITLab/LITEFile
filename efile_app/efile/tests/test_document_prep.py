from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.drafts import read_upload_data
from efile.workflow import ExistingCase, WorkflowStepKey


def authorize(client, draft):
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session["jurisdiction"] = "illinois"
    session.save()


@pytest.fixture
def document_draft(client, django_user_model):
    user = django_user_model.objects.create_user(username="document-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        existing_case=ExistingCase.NEW,
        court_code="cook:cd",
        case_category_code="100",
        case_type_code="200",
        current_step=WorkflowStepKey.DOCUMENT_CHECKLIST,
    )
    FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.LEAD,
        sort_order=0,
        name="petition.pdf",
    )
    client.force_login(user)
    authorize(client, draft)
    return draft


@pytest.mark.django_db
def test_document_checklist_requires_acknowledgement(client, document_draft):
    response = client.post(reverse("document_checklist", kwargs={"jurisdiction": "illinois"}), {})

    document_draft.refresh_from_db()
    assert response.status_code == 200
    assert document_draft.document_checklist_acknowledged is False
    assert b"Confirm that you have added every document" in response.content


@pytest.mark.django_db
def test_document_checklist_continues_to_organize(client, document_draft):
    response = client.post(
        reverse("document_checklist", kwargs={"jurisdiction": "illinois"}),
        {"documents_complete": "yes"},
    )

    document_draft.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("organize_documents", kwargs={"jurisdiction": "illinois"})
    assert document_draft.document_checklist_acknowledged is True
    assert document_draft.current_step == WorkflowStepKey.ORGANIZE_DOCUMENTS


@pytest.mark.django_db
def test_document_checklist_adds_missing_documents_inline(client, document_draft):
    upload = SimpleUploadedFile("exhibit.pdf", b"%PDF exhibit", content_type="application/pdf")

    with patch("efile.views.document_checklist.upload_files") as upload_files:
        response = client.post(
            reverse("document_checklist", kwargs={"jurisdiction": "illinois"}),
            {"action": "upload", "documents": [upload]},
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    upload_files.assert_called_once()
    assert upload_files.call_args.kwargs["current_step"] == WorkflowStepKey.DOCUMENT_CHECKLIST


@pytest.mark.django_db
def test_organize_requires_completed_checklist(client, document_draft):
    response = client.get(reverse("organize_documents", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 302
    assert response.url == reverse("document_checklist", kwargs={"jurisdiction": "illinois"})


@pytest.mark.django_db
def test_organize_redirects_when_court_is_missing(client, document_draft):
    document_draft.court_code = ""
    document_draft.document_checklist_acknowledged = True
    document_draft.save(update_fields=["court_code", "document_checklist_acknowledged", "updated_at"])

    response = client.get(reverse("organize_documents", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 302
    assert response.url == reverse("extraction_review", kwargs={"jurisdiction": "illinois"})


@pytest.mark.django_db
def test_organize_returns_to_review_when_edited_from_there(client, document_draft):
    document_draft.document_checklist_acknowledged = True
    document_draft.save(update_fields=["document_checklist_acknowledged", "updated_at"])
    lead = document_draft.documents.get(role=FilingDocument.Role.LEAD)
    details = [
        {
            "id": lead.pk,
            "name": "Petition",
            "filing_type": "petition",
            "filing_type_name": "Petition",
            "document_type": "public",
            "document_type_name": "No (Public)",
            "filing_component": "lead",
            "filing_component_name": "Lead Document",
        },
    ]

    response = client.post(
        reverse("organize_documents", kwargs={"jurisdiction": "illinois"}),
        {"documents": details, "main_document_id": lead.pk, "return_to": "review"},
        content_type="application/json",
    )

    document_draft.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["redirect_url"] == reverse("case_review", kwargs={"jurisdiction": "illinois"})
    assert document_draft.current_step == WorkflowStepKey.REVIEW


@pytest.mark.django_db
def test_organize_shows_no_radio_choice_for_a_single_document(client, document_draft):
    document_draft.document_checklist_acknowledged = True
    document_draft.save(update_fields=["document_checklist_acknowledged", "updated_at"])
    lead = document_draft.documents.get(role=FilingDocument.Role.LEAD)

    response = client.get(reverse("organize_documents", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "only document in this filing" in content
    assert 'type="radio"' not in content
    assert f'name="main_document" value="{lead.pk}"' in content


@pytest.mark.django_db
def test_organize_shows_radio_choice_for_multiple_documents(client, document_draft):
    document_draft.document_checklist_acknowledged = True
    document_draft.save(update_fields=["document_checklist_acknowledged", "updated_at"])
    FilingDocument.objects.create(
        draft=document_draft,
        role=FilingDocument.Role.SUPPORTING,
        sort_order=0,
        name="exhibit.pdf",
    )

    response = client.get(reverse("organize_documents", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "only document in this filing" not in content
    assert content.count('type="radio"') == 2


@pytest.mark.django_db
def test_organize_saves_details_and_supporting_order(client, document_draft):
    first = FilingDocument.objects.create(
        draft=document_draft,
        role=FilingDocument.Role.SUPPORTING,
        sort_order=0,
        name="first.pdf",
    )
    second = FilingDocument.objects.create(
        draft=document_draft,
        role=FilingDocument.Role.SUPPORTING,
        sort_order=1,
        name="second.pdf",
    )
    lead = document_draft.documents.get(role=FilingDocument.Role.LEAD)
    document_draft.document_checklist_acknowledged = True
    document_draft.save(update_fields=["document_checklist_acknowledged", "updated_at"])
    details = [
        {
            "id": lead.pk,
            "name": "Petition for name change",
            "filing_type": "petition",
            "filing_type_name": "Petition",
            "document_type": "public",
            "document_type_name": "No (Public)",
            "filing_component": "lead",
            "filing_component_name": "Lead Document",
            "courtesy_copy_email": "filer@example.com",
            "requested_optional_services": ["certified"],
            "requires_amount_in_controversy": True,
        },
        {
            "id": second.pk,
            "name": "Exhibit B",
            "filing_type": "exhibit",
            "filing_type_name": "Exhibit",
            "document_type": "sealed",
            "document_type_name": "Yes (Confidential)",
            "filing_component": "attachment",
            "filing_component_name": "Attachments",
            "courtesy_copy_email": "",
        },
        {
            "id": first.pk,
            "name": "Exhibit A",
            "filing_type": "exhibit",
            "filing_type_name": "Exhibit",
            "document_type": "public",
            "document_type_name": "No (Public)",
            "filing_component": "attachment",
            "filing_component_name": "Attachments",
            "courtesy_copy_email": "",
        },
    ]

    response = client.post(
        reverse("organize_documents", kwargs={"jurisdiction": "illinois"}),
        {"documents": details, "main_document_id": second.pk},
        content_type="application/json",
    )

    document_draft.refresh_from_db()
    lead.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["redirect_url"] == reverse("your_information", kwargs={"jurisdiction": "illinois"})
    assert document_draft.current_step == WorkflowStepKey.YOUR_INFORMATION
    assert lead.role == FilingDocument.Role.SUPPORTING
    assert lead.filing_type_code == "petition"
    assert lead.courtesy_copy_email == "filer@example.com"
    assert lead.requested_optional_services == ["certified"]
    assert lead.filing_requires_amount_in_controversy is True
    assert list(
        document_draft.documents.filter(role=FilingDocument.Role.SUPPORTING)
        .order_by("sort_order")
        .values_list("pk", flat=True)
    ) == [lead.pk, first.pk]

    second.refresh_from_db()
    assert second.role == FilingDocument.Role.LEAD

    saved = read_upload_data(document_draft)
    assert saved["lead_filing_component"] == "attachment"
    assert saved["supporting_documents"][0]["filing_type"] == "petition"
