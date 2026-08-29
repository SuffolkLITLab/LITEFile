"""Queue and process durable lead-document extraction jobs."""

import logging
import re
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import perf_counter

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from markitdown import MarkItDown
from pypdf import PdfReader, PdfWriter

from efile.models import DocumentExtraction, FilingDocument
from efile.services.extraction_fields import (
    EXTRACTION_FIELDS,
    EXTRACTION_HINTS,
    display_extracted_fields,
    normalize_document_evidence,
)
from efile.services.taxonomy_classification import (
    HierarchicalDocumentClassifier,
    deterministic_form_identity,
    exact_form_crosswalk_matches,
    primary_amount_in_controversy,
    scan_document_for_form_identifiers,
    summarize_form_crosswalk_matches,
)
from efile.utils.llms import extract_fields_from_file, get_default_model
from efile.utils.prompt_config import prompt_version
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
            "evidence": {},
            "classification": {},
            "analysis_metadata": {},
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


def _searchable_pdf_text(file_path):
    """Extract selectable text cheaply for the deterministic form-ID pass."""
    reader = PdfReader(file_path)
    return "\f".join(page.extract_text() or "" for page in reader.pages)


def _source_text(file_path):
    """Convert the leading pages to text on this machine, sending nothing out."""
    source_pages = max(1, settings.DOCUMENT_CLASSIFICATION_SOURCE_PAGES)
    with limited_pdf(file_path, source_pages) as (source_path, _total, pages_converted):
        return MarkItDown().convert(source_path).text_content, pages_converted


def _form_identifier_pass(file_path, jurisdiction, source_text):
    """Look for registry form IDs printed in the document's own text.

    No model is involved: this is a keyword scan of text the PDF already
    carries, so it runs whether or not the filer allows AI.
    """
    scan_started = perf_counter()
    searchable_text = _searchable_pdf_text(file_path)
    scan = scan_document_for_form_identifiers(jurisdiction, searchable_text)
    scan_source = "pypdf"
    if scan["status"] == "unmatched" and source_text:
        markitdown_scan = scan_document_for_form_identifiers(jurisdiction, source_text)
        if markitdown_scan["status"] != "unmatched":
            scan = markitdown_scan
            scan_source = "markitdown"
    scan_ms = round((perf_counter() - scan_started) * 1000, 2)
    return scan, scan_source, scan_ms, searchable_text


# A label that introduces a case number, followed by the number itself. Courts
# and filers write the label many ways ("Case No.", "Docket Number", "Civil
# Action No."), and OCR turns it into things like "Docker number", so the label
# is matched loosely. The value is not: it is read as a short run of
# alphanumeric chunks, and anything that never shows a digit is discarded, so a
# blank line on an unfilled form is not mistaken for a case number.
_CASE_NUMBER = re.compile(
    r"\b(?:civil\s+action|dock\w*|case)[ \t]*(?:numbers?|no\b\.?|#)[ \t]*[:.\-]?[ \t]*(?:\r?\n[ \t]*){0,2}"
    r"(?P<value>[A-Za-z0-9][A-Za-z0-9./-]*(?:[ -][A-Za-z0-9][A-Za-z0-9./-]*){0,2})",
    re.IGNORECASE,
)


def _looks_like_case_number(candidate):
    """Whether a labelled value is a case number rather than the prose after a label.

    Court forms print the label in their instructions too ("Enter the Case
    Number given by the Circuit Clerk"), so the value has to look the part: it
    starts with a numbered chunk, carries at least two digits, and any further
    chunk is either numbered as well or a short division code, as in
    ``2024 SC 000456``.
    """

    chunks = candidate.split()
    if not chunks or not any(character.isdigit() for character in chunks[0]):
        return False
    if any(len(chunk) > 4 and not any(character.isdigit() for character in chunk) for chunk in chunks[1:]):
        return False
    return sum(character.isdigit() for character in candidate) >= 2


def keyword_case_number(text):
    """Read a printed case number out of labelled text, or return an empty string."""
    for match in _CASE_NUMBER.finditer(text or ""):
        chunks = match.group("value").split()
        # Whatever follows the number on the same line -- a party name, the
        # next label -- is not part of it.
        while chunks and not any(character.isdigit() for character in chunks[-1]):
            chunks.pop()
        candidate = " ".join(chunks).strip(" .-/")
        if _looks_like_case_number(candidate):
            return candidate
    return ""


def keyword_document_analysis(file_path, jurisdiction):
    """Identify a document without any AI, for a filer who opted out.

    Everything here reads the PDF locally: the printed form identifier is
    matched against the form registry, a printed case number is read from its
    label, and the form's own crosswalk entry supplies the court's category and
    type names when it names exactly one of each. Those are recommendations the
    filer still confirms on the review screen, exactly as the AI ones are.
    """
    source_text, pages_converted = _source_text(file_path)
    scan, scan_source, scan_ms, searchable_text = _form_identifier_pass(file_path, jurisdiction, source_text)

    evidence = {}
    matched_form = scan["deterministic_match"] if scan.get("deterministic") else None
    if matched_form:
        evidence["form identifier"] = matched_form["form_id"]
        if matched_form.get("form_name"):
            evidence["form name"] = matched_form["form_name"]
    case_number = keyword_case_number(searchable_text) or keyword_case_number(source_text)
    if case_number:
        evidence["docket number"] = case_number

    identity = deterministic_form_identity(jurisdiction, evidence)
    crosswalk = exact_form_crosswalk_matches(jurisdiction, evidence)
    crosswalk_summary = summarize_form_crosswalk_matches(crosswalk, identity_status=identity["status"])
    guesses = display_extracted_fields(evidence)
    for level, summary_key in (
        ("case category", "category"),
        ("case type", "case_type"),
        ("filing type", "filing_type"),
    ):
        if crosswalk_summary["level_status"].get(summary_key) == "resolved":
            guesses[level] = crosswalk_summary[f"{summary_key}_candidates"][0]

    return {
        "guesses": guesses,
        "evidence": evidence,
        # No live taxonomy selection is possible without a court, and choosing
        # one is the filer's job on the next screen. The names above are what
        # the review screen's dropdowns recommend from.
        "classification": {},
        "metadata": {
            "analysis_mode": "keyword",
            "ai_assistance": "opted_out",
            "source_conversion": "markitdown",
            "source_pages": pages_converted,
            "form_identifier_scan": scan,
            "form_identifier_scan_source": scan_source,
            "form_identifier_scan_ms": scan_ms,
            "form_identity_status": identity["status"],
            "crosswalk_match_count": len(crosswalk),
            "form_crosswalk_summary": crosswalk_summary,
        },
    }


def analyze_document(file_path, jurisdiction, *, use_ai=True):
    """Run vision evidence extraction, source-text conversion, and live classification.

    ``use_ai=False`` is the filer's opt-out (issue #104): it takes the keyword
    path instead, which never sends the document to a model.
    """
    if not use_ai:
        return keyword_document_analysis(file_path, jurisdiction)

    source_text, pages_converted = _source_text(file_path)
    form_identifier_scan, scan_source, scan_ms, _searchable_text = _form_identifier_pass(
        file_path, jurisdiction, source_text
    )

    evidence_prompt = "document_evidence_extraction"
    evidence_version, _definition, evidence_config = prompt_version(evidence_prompt)
    evidence_model = getattr(settings, "DOCUMENT_EVIDENCE_MODEL", "") or get_default_model(
        evidence_config.get("preferred_model_tier", "small")
    )
    evidence_diagnostics = {}
    evidence = normalize_document_evidence(
        extract_fields_from_file(
            file_path,
            EXTRACTION_FIELDS.get(jurisdiction, EXTRACTION_FIELDS["default"]),
            llm_hint=EXTRACTION_HINTS.get(jurisdiction, EXTRACTION_HINTS["default"]),
            model=evidence_model,
            prompt_name=evidence_prompt,
            prompt_version_name=evidence_version,
            diagnostics=evidence_diagnostics,
        )
    )
    ai_form_identifier = evidence.get("form identifier")
    if form_identifier_scan.get("deterministic"):
        # The printed identifier found in the source text is stronger than an
        # AI transcription of the same field. Keep the AI value in metadata for
        # review and diagnostics, but classify from the deterministic value.
        evidence["form identifier"] = form_identifier_scan["deterministic_match"]["form_id"]
    classification = HierarchicalDocumentClassifier().classify(jurisdiction, evidence, source_text)
    guesses = display_extracted_fields(evidence)
    for level, selection in classification.selections.items():
        if selection.get("status") == "selected":
            guesses[level] = selection["name"]
    return {
        "guesses": guesses,
        "evidence": evidence,
        "classification": classification.selections,
        "metadata": {
            "analysis_mode": "ai",
            "evidence_prompt": evidence_prompt,
            "evidence_prompt_version": evidence_version,
            "evidence_model": evidence_model,
            "evidence_input_mode": evidence_diagnostics.get("input_mode", "unknown"),
            "source_conversion": "markitdown",
            "source_pages": pages_converted,
            "form_identifier_scan": form_identifier_scan,
            "form_identifier_scan_source": scan_source,
            "form_identifier_scan_ms": scan_ms,
            "ai_form_identifier": ai_form_identifier,
            **classification.metadata,
        },
    }


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
            analysis = analyze_document(
                analysis_path,
                document.draft.jurisdiction,
                use_ai=not document.draft.ai_assistance_opted_out,
            )

    # Keep compatibility with extensions that still return the old flat shape.
    if "guesses" in analysis and isinstance(analysis.get("guesses"), dict):
        guesses = analysis["guesses"]
        evidence = analysis.get("evidence") if isinstance(analysis.get("evidence"), dict) else {}
        classification = analysis.get("classification") if isinstance(analysis.get("classification"), dict) else {}
        metadata = analysis.get("metadata") if isinstance(analysis.get("metadata"), dict) else {}
    else:
        guesses = analysis
        evidence = {}
        classification = {}
        metadata = {"pipeline": "legacy-flat-result"}

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
            update_fields = ["extracted_guesses", "updated_at"]
            amount = primary_amount_in_controversy(evidence)
            if amount and not draft.amount_in_controversy:
                draft.amount_in_controversy = amount
                update_fields.append("amount_in_controversy")
            draft.save(update_fields=update_fields)
        job.status = DocumentExtraction.Status.COMPLETE
        job.total_pages = total_pages
        job.pages_analyzed = pages_analyzed
        job.evidence = evidence
        job.classification = classification
        job.analysis_metadata = metadata
        job.error = ""
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "total_pages",
                "pages_analyzed",
                "evidence",
                "classification",
                "analysis_metadata",
                "error",
                "completed_at",
                "updated_at",
            ]
        )
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
