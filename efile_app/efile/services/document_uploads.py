import logging
import os
from tempfile import NamedTemporaryFile

from efile.models import FilingDocument
from efile.services.drafts import read_upload_data, write_upload_data
from efile.utils.llms import LlmError, extract_fields_from_file
from efile.utils.s3_upload_handler import S3UploadHandler
from efile.views.session_api import llm_fields, llm_hints
from efile.workflow import WorkflowStepKey

logger = logging.getLogger(__name__)


def _analyze_lead(uploaded_file, jurisdiction):
    temp_path = None
    try:
        uploaded_file.seek(0)
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name
        return extract_fields_from_file(
            temp_path,
            llm_fields.get(jurisdiction, llm_fields["default"]),
            llm_hint=llm_hints.get(jurisdiction, llm_hints["default"]),
        )
    except LlmError:
        logger.exception("Document extraction failed")
        return {}
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.warning("Could not remove extraction temp file %s", temp_path)


def _guess_payload(found_fields):
    return {
        "court": found_fields.get("court name"),
        "filing type": found_fields.get("filing type"),
        "case category": found_fields.get("case category"),
        "case type": found_fields.get("case type"),
        "docket number": found_fields.get("docket number") or found_fields.get("docker number"),
    }


def upload_files(draft, uploaded_files, jurisdiction, *, current_step=WorkflowStepKey.UPLOAD_DOCUMENTS):
    """Upload PDFs and merge them into the draft without discarding existing files."""

    handler = S3UploadHandler()
    if not handler._ensure_initialized():
        raise ValueError("Document storage is not configured. Please try again later.")

    current = read_upload_data(draft)
    files = current.setdefault("files", {})
    supporting = list(files.get("supporting", []))
    lead_file = None

    for uploaded_file in uploaded_files:
        validation = handler.validate_file(uploaded_file, max_size_mb=10, allowed_types=[".pdf"])
        if not validation["valid"]:
            raise ValueError(f"{uploaded_file.name}: {validation['error']}")

        is_lead = not files.get("lead") and lead_file is None
        role = FilingDocument.Role.LEAD if is_lead else FilingDocument.Role.SUPPORTING
        uploaded_file.seek(0)
        result = handler.upload_file(uploaded_file, file_type=role)
        if not result["success"]:
            raise ValueError(result.get("error", f"Could not upload {uploaded_file.name}."))

        file_data = {
            "name": uploaded_file.name,
            "size": uploaded_file.size,
            "type": uploaded_file.content_type,
            "url": handler.get_public_url(result["key"]),
            "s3_key": result["key"],
        }
        if is_lead:
            files["lead"] = file_data
            lead_file = uploaded_file
        else:
            supporting.append(file_data)

    files["supporting"] = supporting
    if lead_file is not None:
        current["guesses"] = _guess_payload(_analyze_lead(lead_file, jurisdiction))
    write_upload_data(draft, current, current_step=current_step)
    return current
