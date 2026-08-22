from efile.models import FilingDocument
from efile.services.document_extractions import queue_document_extraction
from efile.services.drafts import read_upload_data, write_upload_data
from efile.utils.s3_upload_handler import S3UploadHandler
from efile.workflow import WorkflowStepKey


def upload_files(draft, uploaded_files, jurisdiction, *, current_step=WorkflowStepKey.UPLOAD_DOCUMENTS):
    """Upload PDFs immediately and queue lead analysis outside the request."""

    handler = S3UploadHandler()
    if not handler._ensure_initialized():
        raise ValueError("Document storage is not configured. Please try again later.")

    current = read_upload_data(draft)
    files = current.setdefault("files", {})
    supporting = list(files.get("supporting", []))
    found_lead = False

    for uploaded_file in uploaded_files:
        validation = handler.validate_file(uploaded_file, max_size_mb=10, allowed_types=[".pdf"])
        if not validation["valid"]:
            raise ValueError(f"{uploaded_file.name}: {validation['error']}")

        is_lead = not files.get("lead") and not found_lead
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
            found_lead = True
            current["guesses"] = {}
        else:
            supporting.append(file_data)

    files["supporting"] = supporting
    write_upload_data(draft, current, current_step=current_step)
    if found_lead:
        lead = FilingDocument.objects.get(draft=draft, role=FilingDocument.Role.LEAD)
        queue_document_extraction(lead)
    return current
