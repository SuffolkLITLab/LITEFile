"""Queue and process durable lead-document extraction jobs."""

import logging
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from pypdf import PdfReader, PdfWriter

from efile.models import DocumentExtraction, FilingDocument
from efile.services.extraction_fields import EXTRACTION_FIELDS, EXTRACTION_HINTS, normalize_extracted_fields
from efile.utils.llms import extract_fields_from_file
from efile.utils.s3_upload_handler import S3UploadHandler

logger = logging.getLogger(__name__)


def queue_document_extraction(document):
    """Create or reset the one background extraction job for a lead PDF."""
    if document.role != FilingDocument.Role.LEAD:
        raise ValueError("Only a lead document can be analyzed")
    job, _created = DocumentExtraction.objects.update_or_create(
        document=document,
        defaults={
            "status": DocumentExtraction.Status.PENDING,
            "attempts": 0,
            "total_pages": None,
            "pages_analyzed": None,
            "error": "",
            "started_at": None,
            "completed_at": None,
        },
    )
    return job


def extraction_for_document(document):
    try:
        return document.extraction
    except DocumentExtraction.DoesNotExist:
        return None


@contextmanager
def limited_pdf(source_path, max_pages):
    """Yield a PDF containing at most ``max_pages`` and its page counts."""
    reader = PdfReader(source_path)
    total_pages = len(reader.pages)
    pages_analyzed = min(total_pages, max_pages)
    if total_pages <= max_pages:
        yield source_path, total_pages, pages_analyzed
        return

    temp_path = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".pdf") as limited_file:
            writer = PdfWriter()
            for page in reader.pages[:max_pages]:
                writer.add_page(page)
            writer.write(limited_file)
            temp_path = limited_file.name
        yield temp_path, total_pages, pages_analyzed
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


def analyze_document(file_path, jurisdiction):
    return normalize_extracted_fields(
        extract_fields_from_file(
            file_path,
            EXTRACTION_FIELDS.get(jurisdiction, EXTRACTION_FIELDS["default"]),
            llm_hint=EXTRACTION_HINTS.get(jurisdiction, EXTRACTION_HINTS["default"]),
        )
    )


def process_document_extraction(job_id):
    """Download, page-limit, and analyze one job already claimed by a worker."""
    job = DocumentExtraction.objects.select_related("document__draft").get(pk=job_id)
    document = job.document
    handler = S3UploadHandler()

    with TemporaryDirectory(prefix="litefile-extraction-") as temp_dir:
        source_path = str(Path(temp_dir) / "lead.pdf")
        download = handler.download_file(document.s3_key, source_path)
        if not download.get("success"):
            raise RuntimeError(download.get("error") or "Could not read the uploaded PDF")

        max_pages = max(1, settings.DOCUMENT_EXTRACTION_MAX_PAGES)
        with limited_pdf(source_path, max_pages) as (analysis_path, total_pages, pages_analyzed):
            guesses = analyze_document(analysis_path, document.draft.jurisdiction)

    with transaction.atomic():
        job = DocumentExtraction.objects.select_for_update().select_related("document__draft").filter(pk=job_id).first()
        if job is None:
            return None
        document = job.document
        # A filer can remove or replace the lead while this worker is running.
        # Never let the old document overwrite the new lead's extraction.
        is_current_lead = FilingDocument.objects.filter(
            pk=document.pk,
            draft=document.draft,
            role=FilingDocument.Role.LEAD,
        ).exists()
        if is_current_lead:
            draft = document.draft
            draft.extracted_guesses = guesses
            draft.save(update_fields=["extracted_guesses", "updated_at"])
        job.status = DocumentExtraction.Status.COMPLETE
        job.total_pages = total_pages
        job.pages_analyzed = pages_analyzed
        job.error = ""
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "total_pages", "pages_analyzed", "error", "completed_at", "updated_at"])
    return job


def claim_next_extraction(stale_after_minutes=15):
    """Atomically claim one pending or interrupted job for this worker."""
    max_attempts = settings.DOCUMENT_EXTRACTION_MAX_ATTEMPTS
    stale_before = timezone.now() - timedelta(minutes=stale_after_minutes)
    candidates = DocumentExtraction.objects.filter(attempts__lt=max_attempts).filter(
        Q(status=DocumentExtraction.Status.PENDING)
        | Q(status=DocumentExtraction.Status.PROCESSING, started_at__lt=stale_before)
    )
    with transaction.atomic():
        if connection.features.has_select_for_update_skip_locked:
            candidates = candidates.select_for_update(skip_locked=True)
        else:
            candidates = candidates.select_for_update()
        job = candidates.order_by("created_at").first()
        if job is None:
            return None
        job.status = DocumentExtraction.Status.PROCESSING
        job.attempts += 1
        job.started_at = timezone.now()
        job.error = ""
        job.save(update_fields=["status", "attempts", "started_at", "error", "updated_at"])
        return job


def record_extraction_failure(job_id, error):
    """Retry transient failures, then expose a manual-entry fallback."""
    with transaction.atomic():
        job = DocumentExtraction.objects.select_for_update().filter(pk=job_id).first()
        if job is None:
            return None
        retry = job.attempts < settings.DOCUMENT_EXTRACTION_MAX_ATTEMPTS
        job.status = DocumentExtraction.Status.PENDING if retry else DocumentExtraction.Status.FAILED
        job.error = str(error)[:2000]
        job.completed_at = None if retry else timezone.now()
        job.save(update_fields=["status", "error", "completed_at", "updated_at"])
    return job
