import io
import logging

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBase
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument
from efile.services.current_drafts import ensure_current_draft, get_current_draft
from efile.services.document_preparation import PreparationError, PreparationUnavailable
from efile.services.document_previews import (
    DocumentReviewError,
    approve_document_review,
    prepare_document_review,
    preview_fingerprint,
)
from efile.utils.s3_upload_handler import S3UploadHandler
from efile.workflow import WorkflowStepKey, continue_url, get_workflow_context, return_target

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def preview_documents(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)
    draft = ensure_current_draft(request, jurisdiction, current_step=WorkflowStepKey.PREVIEW_DOCUMENTS)
    if not FilingDocument.objects.filter(draft=draft).exists():
        return redirect("upload_documents", jurisdiction=jurisdiction)
    return_to = return_target(request)
    error = ""
    status = 200
    if request.method == "GET":
        try:
            prepare_document_review(draft, S3UploadHandler())
        except PreparationUnavailable as exc:
            error, status = str(exc), 503
        except PreparationError as exc:
            error, status = str(exc), 422
        except (BotoCoreError, ClientError):
            error, status = "We could not load your files. Try again later.", 503
    if request.method == "POST":
        try:
            approve_document_review(draft, request.POST.get("preview_fingerprint"))
        except DocumentReviewError as exc:
            error, status = str(exc), exc.status
        else:
            return redirect(continue_url(draft, jurisdiction, return_to, WorkflowStepKey.EXTRACTION_REVIEW))
    documents = list(FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "pk"))
    context = {
        "documents": documents,
        "preview_fingerprint": preview_fingerprint(documents),
        "preview_error": error,
        "preparation_pending": any(not doc.preparation for doc in documents),
        "return_to": return_to,
        "is_logged_in": True,
    }
    context.update(get_workflow_context(WorkflowStepKey.PREVIEW_DOCUMENTS, jurisdiction, draft))
    return render(request, "efile/preview_documents.html", context, status=status)


@require_http_methods(["GET"])
def document_content(request, jurisdiction, document_id) -> HttpResponseBase:
    """Serve current private bytes to PDF.js without exposing or trusting URLs."""
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return HttpResponse("Sign in again to view this document.", status=401)
    draft = get_current_draft(request, jurisdiction=jurisdiction, resume_latest=False)
    document = FilingDocument.objects.filter(draft=draft, pk=document_id).first() if draft else None
    if document is None:
        raise Http404
    original = request.GET.get("original") == "1"
    key = (document.original_s3_key or document.s3_key) if original else document.s3_key
    if not key:
        raise Http404
    handler = S3UploadHandler()
    if not handler._ensure_initialized() or handler.s3_client is None:
        return HttpResponse("We could not load this file. Try again.", status=503)
    try:
        result = handler.s3_client.get_object(Bucket=handler.bucket_name, Key=key)
        body = result["Body"]
        try:
            content = body.read(settings.MAX_FILE_SIZE + 1)
        finally:
            body.close()
        if len(content) > settings.MAX_FILE_SIZE:
            return HttpResponse("This document is too large to preview.", status=413)
    except (BotoCoreError, ClientError):
        logger.warning("Could not load document %s for preview", document.pk)
        return HttpResponse("We could not load this file. Try again.", status=503)
    filename = document.original_filename if original else (document.name or document.original_filename)
    is_pdf = content.startswith(b"%PDF-")
    if not original and not is_pdf:
        return HttpResponse("We could not read this PDF. Upload a new copy.", status=422)
    if is_pdf and not original and not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    response = FileResponse(
        io.BytesIO(content),
        as_attachment=original or request.GET.get("download") == "1",
        filename=filename,
        content_type="application/pdf" if is_pdf else "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
