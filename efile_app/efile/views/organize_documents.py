import json

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.workflow import ExistingCase, WorkflowStepKey, get_step_url, get_workflow_context


@transaction.atomic
def _save_document_details(draft, document_details):
    documents = {document.pk: document for document in FilingDocument.objects.select_for_update().filter(draft=draft)}
    if {item.get("id") for item in document_details} != set(documents):
        raise ValueError("The document list changed. Refresh the page and try again.")

    # Move supporting documents out of the final range before applying a new
    # order, so swapping positions cannot trip the unique (draft, role, order)
    # constraint halfway through the transaction.
    for document in documents.values():
        if document.role == FilingDocument.Role.SUPPORTING:
            FilingDocument.objects.filter(pk=document.pk).update(sort_order=1_000_000 + document.pk)

    supporting_order = 0
    for item in document_details:
        document = documents[item["id"]]
        filing_type = str(item.get("filing_type") or "").strip()
        document_type = str(item.get("document_type") or "").strip()
        if not filing_type or not document_type:
            raise ValueError(f"Choose a filing type and confidentiality setting for {document.name}.")

        document.name = str(item.get("name") or "").strip()[:255] or document.name
        document.filing_type_code = filing_type
        document.filing_type_name = str(item.get("filing_type_name") or "")[:255]
        document.document_type_code = document_type
        document.document_type_name = str(item.get("document_type_name") or "")[:255]
        document.filing_component_code = str(item.get("filing_component") or "")[:100]
        document.filing_component_name = str(item.get("filing_component_name") or "")[:255]
        document.courtesy_copy_email = str(item.get("courtesy_copy_email") or "")[:254]
        if document.role == FilingDocument.Role.SUPPORTING:
            document.sort_order = supporting_order
            supporting_order += 1
        document.save()


@require_http_methods(["GET", "POST"])
def organize_documents(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.ORGANIZE_DOCUMENTS,
        workflow_version=2,
    )
    documents = FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "created_at")
    if not documents.exists():
        return redirect("upload_documents", jurisdiction=jurisdiction)
    if not draft.document_checklist_acknowledged:
        messages.info(request, "Check that you have all of your documents before organizing them.")
        return redirect("document_checklist", jurisdiction=jurisdiction)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            details = data.get("documents")
            if not isinstance(details, list):
                raise ValueError("Document details are missing.")
            _save_document_details(draft, details)
        except (json.JSONDecodeError, ValueError) as error:
            return JsonResponse({"success": False, "error": str(error)}, status=400)

        draft.current_step = WorkflowStepKey.YOUR_INFORMATION
        draft.save(update_fields=["current_step", "updated_at"])
        return JsonResponse(
            {
                "success": True,
                "redirect_url": get_step_url(WorkflowStepKey.YOUR_INFORMATION, jurisdiction),
            }
        )

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "documents": documents,
        "organize_context": {
            "jurisdiction": jurisdiction,
            "court": draft.court_code,
            "case_category": draft.case_category_code,
            "case_type": draft.case_type_code,
            "existing_case": "yes" if draft.existing_case == ExistingCase.EXISTING else "no",
            "guessed_filing_type": (draft.extracted_guesses or {}).get("filing type", ""),
        },
    }
    context.update(get_workflow_context(WorkflowStepKey.ORGANIZE_DOCUMENTS, jurisdiction, draft))
    return render(request, "efile/organize_documents.html", context)
