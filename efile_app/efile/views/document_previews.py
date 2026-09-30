import io
import logging

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBase
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument, FilingDraft
from efile.services.current_drafts import ensure_current_draft, get_current_draft
from efile.services.document_previews import preview_fingerprint
from efile.utils.s3_upload_handler import S3UploadHandler
from efile.workflow import WorkflowStepKey, get_workflow_context

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def preview_documents(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)
    draft = ensure_current_draft(request, jurisdiction, current_step=WorkflowStepKey.PREVIEW_DOCUMENTS)
    if not FilingDocument.objects.filter(draft=draft).exists():
        return redirect("upload_documents", jurisdiction=jurisdiction)
    # These destinations are server-defined, including documents added later
    # from the checklist or fees screen. Never use an arbitrary return URL.
    destinations = {"review": "case_review", "payment": "payment", "document_checklist": "document_checklist"}
    return_to = request.POST.get("return_to") or request.GET.get("return_to", "")
    error = ""
    if request.method == "POST":
        with transaction.atomic():
            draft = FilingDraft.objects.select_for_update().get(pk=draft.pk)
            documents = list(FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "pk"))
            acknowledged = set(request.POST.getlist("reviewed_document"))
            if draft.status not in {FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR}:
                return HttpResponse("This filing is no longer available to edit.", status=409)
            if request.POST.get("preview_fingerprint") != preview_fingerprint(documents):
                error = "Your documents changed. Preview the current copies before continuing."
            elif any(str(doc.pk) not in acknowledged for doc in documents):
                error = "Confirm that you checked each PDF before continuing."
            else:
                FilingDocument.objects.filter(draft=draft).update(preparation_reviewed_at=timezone.now())
                return redirect(destinations.get(return_to, "extraction_review"), jurisdiction=jurisdiction)
    documents = list(FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "pk"))
    context = {
        "documents": documents,
        "preview_fingerprint": preview_fingerprint(documents),
        "preview_error": error,
        "return_to": return_to,
        "is_logged_in": True,
    }
    context.update(get_workflow_context(WorkflowStepKey.PREVIEW_DOCUMENTS, jurisdiction, draft))
    return render(request, "efile/preview_documents.html", context)


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
        return HttpResponse("Document storage is unavailable. Please try again.", status=503)
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
        return HttpResponse("We could not load this document. Please try again.", status=503)
    filename = document.original_filename if original else (document.name or document.original_filename)
    is_pdf = content.startswith(b"%PDF-")
    if not original and not is_pdf:
        return HttpResponse("This document is not a readable PDF. Replace it before continuing.", status=422)
    response = FileResponse(
        io.BytesIO(content),
        as_attachment=original or request.GET.get("download") == "1",
        filename=filename,
        content_type="application/pdf" if is_pdf else "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
