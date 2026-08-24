import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.urls import reverse
from pypdf import PdfReader, PdfWriter

from efile.models import DocumentExtraction, FilingDocument, FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.document_extractions import (
    claim_next_extraction,
    process_document_extraction,
    queue_document_extraction,
)
from efile.services.extraction_fields import normalize_extracted_fields
from efile.services.taxonomy_classification import ClassificationRun, HierarchicalDocumentClassifier
from efile.workflow import ExistingCase


def authorize(client, draft):
    client.force_login(draft.user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["auth_tokens"] = {f"TYLER-TOKEN-{draft.jurisdiction.upper()}": "token"}
    session["jurisdiction"] = draft.jurisdiction
    session.save()


@pytest.fixture
def extraction_draft(db, django_user_model):
    user = django_user_model.objects.create_user(username="extraction-user", tyler_jurisdiction="illinois")
    return FilingDraft.objects.create(user=user, jurisdiction="illinois", workflow_version=2)


def test_normalization_keeps_every_extracted_field():
    guesses = normalize_extracted_fields(
        {
            "court name": "Washington County",
            "docker number": "24-CV-123",
            "plaintiff or petitioner names": "Alex Rivera; Sam Rivera",
            "other party names": ["Guardian: Pat Lee", "Minor: Casey Lee"],
            "unexpected useful detail": "Shown on page two",
        }
    )

    assert guesses == {
        "court": "Washington County",
        "docket number": "24-CV-123",
        "plaintiff or petitioner names": "Alex Rivera; Sam Rivera",
        "other party names": "Guardian: Pat Lee; Minor: Casey Lee",
        "unexpected useful detail": "Shown on page two",
    }


@pytest.mark.django_db
def test_worker_caps_pages_and_persists_the_complete_payload(extraction_draft):
    document = FilingDocument.objects.create(
        draft=extraction_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
        s3_key="lead/petition.pdf",
    )
    job = queue_document_extraction(document)
    claimed = claim_next_extraction()
    assert claimed.pk == job.pk

    handler = MagicMock()

    def create_download(_key, destination):
        writer = PdfWriter()
        for _index in range(5):
            writer.add_blank_page(width=612, height=792)
        with open(destination, "wb") as pdf_file:
            writer.write(pdf_file)
        return {"success": True}

    handler.download_file.side_effect = create_download

    def inspect_limited_pdf(file_path, _jurisdiction):
        assert len(PdfReader(file_path).pages) == 2
        return {
            "court": "Washington County",
            "document title": "Complaint",
            "plaintiff or petitioner names": "Alex Rivera",
        }

    with (
        override_settings(DOCUMENT_EXTRACTION_MAX_PAGES=2),
        patch("efile.services.document_extractions.S3UploadHandler", return_value=handler),
        patch("efile.services.document_extractions.analyze_document", side_effect=inspect_limited_pdf),
    ):
        process_document_extraction(job.pk)

    job.refresh_from_db()
    extraction_draft.refresh_from_db()
    assert job.status == DocumentExtraction.Status.COMPLETE
    assert job.total_pages == 5
    assert job.pages_analyzed == 2
    assert extraction_draft.extracted_guesses["document title"] == "Complaint"
    assert extraction_draft.extracted_guesses["plaintiff or petitioner names"] == "Alex Rivera"


@pytest.mark.django_db
def test_worker_reads_a_real_uploaded_pdf_before_classification(extraction_draft):
    """Do not let the standard worker test regress to a fully mocked document."""
    source_pdf = Path(__file__).resolve().parents[3] / "benchmarking/synthetic/filled_pdfs/flattened/MA-01.pdf"
    assert source_pdf.is_file()
    document = FilingDocument.objects.create(
        draft=extraction_draft,
        role=FilingDocument.Role.LEAD,
        name="MA-01.pdf",
        s3_key="lead/MA-01.pdf",
    )
    extraction_draft.jurisdiction = "massachusetts"
    extraction_draft.save(update_fields=["jurisdiction", "updated_at"])
    job = queue_document_extraction(document)
    handler = MagicMock()

    def download_real_pdf(_key, destination):
        shutil.copyfile(source_pdf, destination)
        return {"success": True}

    handler.download_file.side_effect = download_real_pdf

    def classify_source(_classifier, jurisdiction, evidence, source_text):
        assert jurisdiction == "massachusetts"
        assert evidence["form identifier"] == "CJD 101B"
        assert "COMPLAINT FOR DIVORCE" in source_text
        assert "Middlesex" in source_text
        assert "Division" in source_text
        return ClassificationRun(
            selections={
                "court": {
                    "status": "selected",
                    "name": "Middlesex Probate and Family Court",
                    "route_key": "current-court-key",
                }
            },
            metadata={"prompt_version": "v2", "model": "test-model"},
        )

    with (
        patch("efile.services.document_extractions.S3UploadHandler", return_value=handler),
        patch(
            "efile.services.document_extractions.extract_fields_from_file",
            return_value={
                "form identifier": "CJD 101B",
                "form name": "Complaint for Divorce under G.L. c. 208, § 1B",
                "court name": "Middlesex Division",
                "filing phase": "initial",
                "monetary amounts": [{"label": "Amount in controversy", "raw": "$1,275", "amount": "1275"}],
            },
        ),
        patch("efile.services.document_extractions.get_default_model", return_value="test-evidence-model"),
        patch.object(HierarchicalDocumentClassifier, "classify", classify_source),
        patch.object(HierarchicalDocumentClassifier, "__init__", return_value=None),
    ):
        process_document_extraction(job.pk)

    job.refresh_from_db()
    extraction_draft.refresh_from_db()
    assert job.evidence["form identifier"] == "CJD 101B"
    assert job.classification["court"]["route_key"] == "current-court-key"
    assert job.analysis_metadata["evidence_prompt_version"] == "v1"
    assert extraction_draft.extracted_guesses["court"] == "Middlesex Probate and Family Court"
    assert extraction_draft.amount_in_controversy == "1275"


@pytest.mark.django_db
def test_review_waits_for_background_analysis(client, extraction_draft):
    authorize(client, extraction_draft)
    document = FilingDocument.objects.create(
        draft=extraction_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
    )
    queue_document_extraction(document)

    response = client.get(reverse("extraction_review", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 302
    assert response.url == reverse("upload_documents", kwargs={"jurisdiction": "illinois"})


@pytest.mark.django_db
def test_status_endpoint_reports_when_review_is_ready(client, extraction_draft):
    authorize(client, extraction_draft)
    document = FilingDocument.objects.create(
        draft=extraction_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
    )
    job = queue_document_extraction(document)
    job.status = DocumentExtraction.Status.COMPLETE
    job.total_pages = 30
    job.pages_analyzed = 20
    job.save(update_fields=["status", "total_pages", "pages_analyzed", "updated_at"])

    response = client.get(reverse("document_extraction_status", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "complete",
        "ready": True,
        "pages_analyzed": 20,
        "total_pages": 30,
        "review_url": reverse("extraction_review", kwargs={"jurisdiction": "illinois"}),
    }


@pytest.mark.django_db
def test_review_shows_every_detail_and_requires_acknowledgment(client, extraction_draft):
    authorize(client, extraction_draft)
    FilingDocument.objects.create(
        draft=extraction_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
    )
    extraction_draft.extracted_guesses = {
        "court": "Washington County",
        "document title": "Complaint",
        "plaintiff or petitioner names": "Alex Rivera",
        "unexpected useful detail": "Shown on page two",
    }
    extraction_draft.save(update_fields=["extracted_guesses", "updated_at"])

    page = client.get(reverse("extraction_review", kwargs={"jurisdiction": "illinois"}))
    content = page.content.decode()
    assert "Document title" in content
    assert "Alex Rivera" in content
    assert "Unexpected useful detail" in content
    assert 'name="reviewed_extraction"' in content

    response = client.post(
        reverse("extraction_review", kwargs={"jurisdiction": "illinois"}),
        {
            "existing_case": ExistingCase.NEW,
            "court_code": "washington",
            "case_category_code": "civil",
            "case_type_code": "small-claims",
        },
    )
    assert response.status_code == 200
    assert "Review all the information pulled" in response.content.decode()


@pytest.mark.django_db
def test_vermont_review_uses_court_form_terms_and_neutral_copy(client, django_user_model):
    user = django_user_model.objects.create_user(username="vermont-reviewer", tyler_jurisdiction="vermont")
    draft = FilingDraft.objects.create(user=user, jurisdiction="vermont", workflow_version=2)
    FilingDocument.objects.create(draft=draft, role=FilingDocument.Role.LEAD, name="complaint.pdf")
    authorize(client, draft)

    content = client.get(reverse("extraction_review", kwargs={"jurisdiction": "vermont"})).content.decode()

    assert "Court unit or county" in content
    assert "Court division" in content
    assert "Civil includes Small Claims" in content
    assert "Family includes Relief from Abuse" in content
    assert "Our system did not pull details from your document" in content
    assert "We could not find any case details" not in content


@pytest.mark.django_db
def test_failed_extraction_allows_review_with_neutral_failure_copy(client, extraction_draft):
    authorize(client, extraction_draft)
    document = FilingDocument.objects.create(
        draft=extraction_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
    )
    job = queue_document_extraction(document)
    job.status = DocumentExtraction.Status.FAILED
    job.error = "Corrupted PDF"
    job.save(update_fields=["status", "error", "updated_at"])

    response = client.get(reverse("extraction_review", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Our system could not pull details from your document." in content
    assert "go back and try a different document" in content


@pytest.mark.django_db
def test_management_command_runs_once_with_no_jobs():
    from django.core.management import call_command

    call_command("process_document_extractions", once=True)


@pytest.mark.django_db
def test_management_command_processes_and_retries_failures(extraction_draft):
    from django.core.management import call_command

    document = FilingDocument.objects.create(
        draft=extraction_draft,
        role=FilingDocument.Role.LEAD,
        name="petition.pdf",
        s3_key="lead/petition.pdf",
    )
    job = queue_document_extraction(document)

    with (
        override_settings(DOCUMENT_EXTRACTION_MAX_ATTEMPTS=2),
        patch(
            "efile.management.commands.process_document_extractions.process_document_extraction",
            side_effect=ValueError("S3 network error"),
        ),
    ):
        # 1st attempt: should fail and reset to PENDING for retry
        call_command("process_document_extractions", once=True)
        job.refresh_from_db()
        assert job.status == DocumentExtraction.Status.PENDING
        assert job.attempts == 1
        assert "S3 network error" in job.error

        # 2nd attempt: reaches max_attempts (2) -> status becomes FAILED
        call_command("process_document_extractions", once=True)
        job.refresh_from_db()
        assert job.status == DocumentExtraction.Status.FAILED
        assert job.attempts == 2
        assert "S3 network error" in job.error
