import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.utils.config_loader import config_loader
from efile.utils.ui_text import get_texts
from efile.workflow import RETURN_TO_REVIEW, ExistingCase, WorkflowStepKey, get_step_url, get_workflow_context

# Strings the organize-documents script renders itself, handed to it through the
# page. Keyed in the JSON by their last path segment: `loading_choices`, and so on.
JS_TEXT_KEYS = [
    "organize_documents.choose_filing_type_first",
    "organize_documents.loading_choices",
    "organize_documents.no_document_types",
    "organize_documents.no_filing_components",
    "organize_documents.filing_component_fixed_note",
    "organize_documents.filing_component_required_note",
]


def _document_id(value):
    """Read a document primary key off the wire, or None if there isn't one.

    ``None`` means "the client did not name one" -- including every shape that
    stands in for an unset numeric field, such as ``NaN``, ``null`` or ``""``.
    Callers fall back rather than treating an unreadable value as an error.
    """
    try:
        document_id = int(value)
    except (TypeError, ValueError):
        return None
    return document_id if document_id > 0 else None


@transaction.atomic
def _save_document_details(draft, document_details, main_document_id):
    documents = {document.pk: document for document in FilingDocument.objects.select_for_update().filter(draft=draft)}
    if {item.get("id") for item in document_details} != set(documents):
        raise ValueError("The document list changed. Refresh the page and try again.")
    if main_document_id not in documents:
        raise ValueError("Choose the main document for this filing.")

    # Move every document out of the final ranges before changing the main
    # document or order, so role/order swaps cannot trip the uniqueness rule.
    for document in documents.values():
        FilingDocument.objects.filter(pk=document.pk).update(sort_order=1_000_000 + document.pk)

    for document in documents.values():
        document.role = FilingDocument.Role.LEAD if document.pk == main_document_id else FilingDocument.Role.SUPPORTING

    supporting_order = 0
    for item in document_details:
        document = documents[item["id"]]
        filing_type = str(item.get("filing_type") or "").strip()
        document_type = str(item.get("document_type") or "").strip()
        if not filing_type:
            raise ValueError(f"Choose a filing type for {document.name}.")

        document.name = str(item.get("name") or "").strip()[:255] or document.name
        document.filing_type_code = filing_type
        document.filing_type_name = str(item.get("filing_type_name") or "")[:255]
        document.document_type_code = document_type
        document.document_type_name = str(item.get("document_type_name") or "")[:255]
        document.filing_component_code = str(item.get("filing_component") or "")[:100]
        document.filing_component_name = str(item.get("filing_component_name") or "")[:255]
        courtesy_copy_email = str(item.get("courtesy_copy_email") or "").strip()[:254]
        if courtesy_copy_email:
            try:
                EmailValidator()(courtesy_copy_email)
            except ValidationError as error:
                raise ValueError(f"Enter a valid courtesy copy email address for {document.name}.") from error
        document.courtesy_copy_email = courtesy_copy_email
        optional_services = item.get("requested_optional_services")
        document.requested_optional_services = (
            [str(code)[:100] for code in optional_services if code] if isinstance(optional_services, list) else []
        )
        document.filing_requires_amount_in_controversy = bool(item.get("requires_amount_in_controversy"))
        if document.pk == main_document_id:
            document.sort_order = 0
        else:
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
    if not draft.court_code:
        # Filing types can't be looked up without a court. Send the filer back
        # to whichever step is responsible for setting one, instead of
        # stranding them here with no way to recover.
        fix_step = (
            WorkflowStepKey.CASE_LOOKUP
            if draft.existing_case == ExistingCase.EXISTING
            else WorkflowStepKey.EXTRACTION_REVIEW
        )
        messages.error(request, "Confirm the court for this filing before organizing your documents.")
        return redirect(get_step_url(fix_step, jurisdiction))

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            details = data.get("documents")
            if not isinstance(details, list):
                raise ValueError("Document details are missing.")
            main_document_id = _document_id(data.get("main_document_id"))
            if main_document_id is None:
                # The client could not name a main document: no radio rendered,
                # a stale script, or one of the sentinels a browser produces for
                # an empty numeric field. Anything unreadable is treated the
                # same, because the draft already knows which document leads.
                lead_doc = documents.filter(role=FilingDocument.Role.LEAD).first() or documents.first()
                if lead_doc is None:
                    raise ValueError("Choose the main document for this filing.")
                main_document_id = lead_doc.id
            _save_document_details(draft, details, main_document_id)
        except (json.JSONDecodeError, ValueError) as error:
            return JsonResponse({"success": False, "error": str(error)}, status=400)

        return_to_review = data.get("return_to") == RETURN_TO_REVIEW
        next_step = WorkflowStepKey.REVIEW if return_to_review else WorkflowStepKey.YOUR_INFORMATION
        draft.current_step = next_step
        draft.save(update_fields=["current_step", "updated_at"])
        return JsonResponse(
            {
                "success": True,
                "redirect_url": get_step_url(next_step, jurisdiction),
            }
        )

    jurisdiction_config = config_loader.load_jurisdiction_config(jurisdiction) or {}
    confidentiality_config = jurisdiction_config.get("document_confidentiality") or {}
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "documents": documents,
        "return_to": request.GET.get("return_to", ""),
        "organize_context": {
            "jurisdiction": jurisdiction,
            "court": draft.court_code,
            "case_category": draft.case_category_code,
            "case_type": draft.case_type_code,
            "existing_case": "yes" if draft.existing_case == ExistingCase.EXISTING else "no",
            "guessed_filing_type": (draft.extracted_guesses or {}).get("filing type", ""),
            "default_confidentiality": confidentiality_config.get("default", ""),
            "return_to": request.GET.get("return_to", ""),
            # The script rewrites these choice lists once the court answers, so
            # the strings it renders have to travel with the page -- otherwise
            # they are the only copy on this screen that no state can reword and
            # no translator can reach.
            "text": get_texts(JS_TEXT_KEYS, jurisdiction=jurisdiction),
        },
    }
    context.update(get_workflow_context(WorkflowStepKey.ORGANIZE_DOCUMENTS, jurisdiction, draft))
    return render(request, "efile/organize_documents.html", context)
