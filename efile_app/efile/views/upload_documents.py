import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import DocumentExtraction, FilingDocument
from efile.services.current_drafts import ensure_current_draft
from efile.services.document_extractions import extraction_for_document, queue_document_extraction
from efile.services.document_uploads import upload_files
from efile.services.drafts import draft_snapshot, read_upload_data
from efile.utils.s3_upload_handler import S3UploadHandler
from efile.workflow import WorkflowStepKey, get_step_url, get_workflow_context

logger = logging.getLogger(__name__)


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
            if document.role == FilingDocument.Role.LEAD:
                replacement = other_documents.order_by("sort_order", "created_at").first()
                if replacement is not None:
                    promote_document = replacement.pk
            document.delete()
            if promote_document is not None:
                replacement = FilingDocument.objects.get(pk=promote_document)
                replacement.role = FilingDocument.Role.LEAD
                replacement.sort_order = 0
                replacement.save(update_fields=["role", "sort_order", "updated_at"])
                queue_document_extraction(replacement)
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
            upload_data = upload_files(draft, uploaded_files, jurisdiction)
        except ValueError as error:
            logger.exception("Upload failed for draft %s", draft.pk)
            return JsonResponse({"success": False, "error": str(error)}, status=400)
        return JsonResponse(
            {
                "success": True,
                "redirect_url": get_step_url(WorkflowStepKey.EXTRACTION_REVIEW, jurisdiction),
                "document_count": FilingDocument.objects.filter(draft=draft).count(),
                "extraction_pending": FilingDocument.objects.filter(
                    draft=draft,
                    role=FilingDocument.Role.LEAD,
                    extraction__status__in=[
                        DocumentExtraction.Status.PENDING,
                        DocumentExtraction.Status.PROCESSING,
                    ],
                ).exists(),
            }
        )

    upload_data = read_upload_data(draft)
    documents = list(FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "created_at"))
    lead = next((document for document in documents if document.role == FilingDocument.Role.LEAD), None)
    extraction = extraction_for_document(lead) if lead else None
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "documents": documents,
        "has_lead_document": lead is not None,
        "extraction": extraction,
        "extraction_pending": extraction is not None
        and extraction.status in {DocumentExtraction.Status.PENDING, DocumentExtraction.Status.PROCESSING},
        "max_extraction_pages": settings.DOCUMENT_EXTRACTION_MAX_PAGES,
        "upload_data": upload_data,
    }
    context.update(get_workflow_context(WorkflowStepKey.UPLOAD_DOCUMENTS, jurisdiction, draft))
    return render(request, "efile/upload_documents.html", context)


@require_http_methods(["GET"])
def document_extraction_status(request, jurisdiction):
    """Poll the current lead's durable background analysis state."""
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return JsonResponse({"success": False, "error": "Sign in again to continue."}, status=401)

    draft = ensure_current_draft(request, jurisdiction, workflow_version=2)
    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    extraction = extraction_for_document(lead) if lead else None
    if extraction is None:
        return JsonResponse({"success": True, "status": "not_queued", "ready": lead is not None})

    return JsonResponse(
        {
            "success": True,
            "status": extraction.status,
            "ready": extraction.status in {DocumentExtraction.Status.COMPLETE, DocumentExtraction.Status.FAILED},
            "pages_analyzed": extraction.pages_analyzed,
            "total_pages": extraction.total_pages,
            "review_url": get_step_url(WorkflowStepKey.EXTRACTION_REVIEW, jurisdiction),
        }
    )
