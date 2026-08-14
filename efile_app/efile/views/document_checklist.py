from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument
from efile.services.current_drafts import ensure_current_draft
from efile.services.document_uploads import upload_files
from efile.services.drafts import draft_snapshot
from efile.workflow import WorkflowStepKey, get_step_url, get_workflow_context


@require_http_methods(["GET", "POST"])
def document_checklist(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.DOCUMENT_CHECKLIST,
        workflow_version=2,
    )
    documents = FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "created_at")
    if not documents.exists():
        messages.error(request, "Upload at least one document before checking your filing.")
        return redirect("upload_documents", jurisdiction=jurisdiction)

    if request.method == "POST" and request.POST.get("action") == "upload":
        uploaded_files = request.FILES.getlist("documents")
        if not uploaded_files:
            return JsonResponse({"success": False, "error": "Choose at least one PDF to add."}, status=400)
        try:
            upload_files(
                draft,
                uploaded_files,
                jurisdiction,
                current_step=WorkflowStepKey.DOCUMENT_CHECKLIST,
            )
        except ValueError as error:
            return JsonResponse({"success": False, "error": str(error)}, status=400)
        if draft.document_checklist_acknowledged:
            draft.document_checklist_acknowledged = False
            draft.save(update_fields=["document_checklist_acknowledged", "updated_at"])
        return JsonResponse({"success": True, "document_count": FilingDocument.objects.filter(draft=draft).count()})

    if request.method == "POST":
        if request.POST.get("documents_complete") != "yes":
            messages.error(request, "Confirm that you have added every document you want to file.")
        else:
            draft.document_checklist_acknowledged = True
            draft.current_step = WorkflowStepKey.ORGANIZE_DOCUMENTS
            draft.save(update_fields=["document_checklist_acknowledged", "current_step", "updated_at"])
            return redirect(get_step_url(WorkflowStepKey.ORGANIZE_DOCUMENTS, jurisdiction))

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "documents": documents,
    }
    context.update(get_workflow_context(WorkflowStepKey.DOCUMENT_CHECKLIST, jurisdiction, draft))
    return render(request, "efile/document_checklist.html", context)
