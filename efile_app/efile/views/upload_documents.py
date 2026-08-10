import logging
import os
from tempfile import NamedTemporaryFile

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, read_upload_data, write_upload_data
from efile.utils.llms import LlmError, extract_fields_from_file
from efile.utils.s3_upload_handler import S3UploadHandler
from efile.views.session_api import llm_fields, llm_hints
from efile.workflow import WorkflowStepKey, get_step_url, get_workflow_context

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


def _upload_files(draft, uploaded_files, jurisdiction):
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
    write_upload_data(draft, current, current_step=WorkflowStepKey.UPLOAD_DOCUMENTS)
    return current


@require_http_methods(["GET", "POST"])
def upload_documents(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.UPLOAD_DOCUMENTS,
        workflow_version=2,
    )

    if request.method == "POST":
        action = request.POST.get("action", "upload")
        if action == "remove":
            document_id = request.POST.get("document_id")
            document = FilingDocument.objects.filter(pk=document_id, draft=draft).first()
            if document is None:
                return JsonResponse({"success": False, "error": "Document not found."}, status=404)
            removed_lead = document.role == FilingDocument.Role.LEAD
            s3_key = document.s3_key
            promote_document = None
            other_documents = FilingDocument.objects.filter(draft=draft).exclude(pk=document.pk)
            if document.role == FilingDocument.Role.LEAD and other_documents.exists():
                replacement = other_documents.order_by("sort_order", "created_at").first()
                assert replacement is not None
                promote_document = replacement.pk
            document.delete()
            if promote_document is not None:
                replacement = FilingDocument.objects.get(pk=promote_document)
                replacement.role = FilingDocument.Role.LEAD
                replacement.sort_order = 0
                replacement.save(update_fields=["role", "sort_order", "updated_at"])
            if removed_lead and draft.extracted_guesses:
                draft.extracted_guesses = {}
                draft.save(update_fields=["extracted_guesses", "updated_at"])
            if s3_key:
                handler = S3UploadHandler()
                if handler._ensure_initialized():
                    deletion = handler.delete_file(s3_key)
                    if not deletion.get("success"):
                        logger.warning("Could not delete removed draft document %s from storage", s3_key)
            return JsonResponse({"success": True})

        uploaded_files = request.FILES.getlist("documents")
        if not uploaded_files:
            return JsonResponse({"success": False, "error": "Choose at least one PDF to upload."}, status=400)
        try:
            upload_data = _upload_files(draft, uploaded_files, jurisdiction)
        except ValueError as error:
            return JsonResponse({"success": False, "error": str(error)}, status=400)
        return JsonResponse(
            {
                "success": True,
                "redirect_url": get_step_url(WorkflowStepKey.EXTRACTION_REVIEW, jurisdiction),
                "document_count": FilingDocument.objects.filter(draft=draft).count(),
            }
        )

    upload_data = read_upload_data(draft)
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "documents": FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "created_at"),
        "has_lead_document": FilingDocument.objects.filter(
            draft=draft,
            role=FilingDocument.Role.LEAD,
        ).exists(),
        "upload_data": upload_data,
    }
    context.update(get_workflow_context(WorkflowStepKey.UPLOAD_DOCUMENTS, jurisdiction, draft))
    return render(request, "efile/upload_documents.html", context)
