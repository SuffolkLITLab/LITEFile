from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument
from efile.services.current_drafts import ensure_current_draft
from efile.services.document_uploads import upload_files
from efile.services.drafts import draft_snapshot
from efile.services.filing_plans import (
    attach_document_to_item,
    attach_lead_document,
    attached_documents,
    checklist_answers_from_post,
    detach_item,
    documents_missing_from_envelope,
    ensure_plan_for_draft,
    filer_role_label,
    filer_roles_for_draft,
    filing_type_for_item,
    grouped_checklist,
    mark_item_have,
    set_checklist_answers,
    set_filer_role,
    status_choices,
)
from efile.workflow import (
    RETURN_TO_REVIEW,
    WorkflowStepKey,
    get_step_url,
    get_workflow_context,
    with_return_to,
)


def _this_page(request, jurisdiction):
    """Reload this step, keeping any "on my way back to Review" marker."""

    return with_return_to(
        get_step_url(WorkflowStepKey.DOCUMENT_CHECKLIST, jurisdiction),
        request.POST.get("return_to") or request.GET.get("return_to"),
    )


def _newest_document(draft):
    """The file just uploaded: an upload appends to the end of the list."""

    return (
        FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.SUPPORTING)
        .order_by("-sort_order", "-pk")
        .first()
        or FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    )


def _attach_to_item(request, draft, plan, jurisdiction):
    """Answer one checklist item with a document, uploading it if need be.

    This is the step that turns the plan from a list into a filing: the filer
    says "this file is my fee waiver", and from then on the checklist, the
    review step, and the envelope all agree about it.
    """

    item_id = request.POST.get("item_id", "")
    if plan is None or item_id not in (plan.checklist or {}):
        messages.error(request, "That document is not on your plan.")
        return redirect(_this_page(request, jurisdiction))

    uploaded_files = request.FILES.getlist("document")
    document_id = request.POST.get("document_id", "")
    label = plan.checklist[item_id].get("label") or item_id

    if uploaded_files:
        try:
            upload_files(draft, uploaded_files, jurisdiction, current_step=WorkflowStepKey.DOCUMENT_CHECKLIST)
        except ValueError as error:
            messages.error(request, str(error))
            return redirect(_this_page(request, jurisdiction))
        document = _newest_document(draft)
        # Adding a file means the filer has more to organize and re-confirm.
        if draft.document_checklist_acknowledged:
            draft.document_checklist_acknowledged = False
            draft.save(update_fields=["document_checklist_acknowledged", "updated_at"])
    else:
        document = FilingDocument.objects.filter(draft=draft, pk=document_id).first() if document_id else None

    if document is None:
        messages.error(request, f"Choose a PDF to add for {label}, or pick a file you already added.")
        return redirect(_this_page(request, jurisdiction))

    attach_document_to_item(draft, item_id, document)
    mark_item_have(plan, item_id)

    # The plan knows what this document is, so it can say what the court calls
    # it. Only ever fills a blank: a filing type the filer chose is theirs.
    if not document.filing_type_code:
        code, name = filing_type_for_item(draft, item_id)
        if code:
            document.filing_type_code = code
            document.filing_type_name = name
            document.save(update_fields=["filing_type_code", "filing_type_name", "updated_at"])

    messages.success(request, f"{label} is in this filing.")
    return redirect(_this_page(request, jurisdiction))


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

    # In a two-sided case the same case type means two different jobs, and the
    # documents follow the side rather than the case. Nothing can be listed
    # until we know which side this filer is on, so that is asked first.
    filer_roles = filer_roles_for_draft(draft)
    if request.method == "POST" and request.POST.get("action") == "set_filer_role":
        if not set_filer_role(draft, request.POST.get("filer_role", "")):
            messages.error(request, "Choose which side of this case you are on.")
        return redirect(_this_page(request, jurisdiction))

    # The plan holds the filer's own list for this matter. It outlives this
    # filing, so it is created here and only read from the draft.
    plan = ensure_plan_for_draft(draft)
    attach_lead_document(draft, plan)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "attach_item":
            return _attach_to_item(request, draft, plan, jurisdiction)
        if action == "detach_item":
            detach_item(draft, request.POST.get("item_id", ""))
            return redirect(_this_page(request, jurisdiction))

        if plan is not None:
            set_checklist_answers(
                plan,
                checklist_answers_from_post(request.POST, plan),
                keep_have=attached_documents(draft).keys(),
            )
        if action == "save_progress":
            messages.success(request, "We saved your document list.")
            return redirect(_this_page(request, jurisdiction))
        if request.POST.get("documents_complete") != "yes":
            messages.error(request, "Confirm that you have added every document you want to file.")
        else:
            draft.document_checklist_acknowledged = True
            # Coming back here from Review to add a document is common now that
            # the review step names what is missing. Go straight back to Review,
            # unless a document still needs a filing type -- organizing is where
            # that is chosen, and the court will not take a filing without it.
            return_to = request.POST.get("return_to", "")
            needs_organizing = documents.filter(Q(filing_type_code="") | Q(document_type_code="")).exists()
            next_step = (
                WorkflowStepKey.REVIEW
                if return_to == RETURN_TO_REVIEW and not needs_organizing
                else WorkflowStepKey.ORGANIZE_DOCUMENTS
            )
            draft.current_step = next_step
            draft.save(update_fields=["document_checklist_acknowledged", "current_step", "updated_at"])
            next_url = get_step_url(next_step, jurisdiction)
            return redirect(with_return_to(next_url, return_to) if next_step != WorkflowStepKey.REVIEW else next_url)

    missing = documents_missing_from_envelope(plan, draft)
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "documents": documents,
        "plan": plan,
        "filer_roles": filer_roles,
        "filer_role": draft.filer_role,
        "filer_role_label": filer_role_label(draft),
        # Normally answered on the confirm-filing step. It can still be
        # unanswered here on the existing-case path, where the case type is not
        # known until after the case lookup, so the question has a home here too.
        "choosing_filer_role": bool(filer_roles) and not draft.filer_role,
        "checklist_groups": grouped_checklist(plan, draft),
        "status_choices": status_choices(),
        "guidance": plan.guidance if plan else {},
        # Only the documents the filer says they have: an unticked "always
        # needed" item is already an empty box on this page, and repeating it
        # here would nag rather than help.
        "ready_to_add": [item for item in missing if item["reason"] == "have"],
        "return_to": request.GET.get("return_to", ""),
    }
    context.update(get_workflow_context(WorkflowStepKey.DOCUMENT_CHECKLIST, jurisdiction, draft))
    return render(request, "efile/document_checklist.html", context)
