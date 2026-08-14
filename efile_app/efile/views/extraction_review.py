from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, write_case_data
from efile.workflow import (
    RETURN_TO_REVIEW,
    ExistingCase,
    WorkflowStepKey,
    get_next_step,
    get_step_url,
    get_workflow_context,
)


def _set_lead_filing_type(draft, filing_type_code, filing_type_name):
    if not filing_type_code:
        return
    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    if lead is None:
        return
    lead.filing_type_code = filing_type_code
    lead.filing_type_name = filing_type_name
    lead.save(update_fields=["filing_type_code", "filing_type_name", "updated_at"])


@require_http_methods(["GET", "POST"])
def extraction_review(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.EXTRACTION_REVIEW,
        workflow_version=2,
    )
    if not FilingDocument.objects.filter(draft=draft).exists():
        messages.error(request, "Upload at least one document before reviewing the filing.")
        return redirect("upload_documents", jurisdiction=jurisdiction)

    if request.method == "POST":
        existing_case = request.POST.get("existing_case", draft.existing_case)
        court_code = request.POST.get("court_code", "")
        case_category_code = request.POST.get("case_category_code", "")
        case_type_code = request.POST.get("case_type_code", "")

        if existing_case not in {ExistingCase.NEW, ExistingCase.EXISTING}:
            messages.error(request, "Choose whether this is a new or existing court case to continue.")
        elif existing_case == ExistingCase.NEW and not (court_code and case_category_code and case_type_code):
            # Tyler's e-filing API only accepts exact court/category/type codes, so
            # a new case can't proceed on free-text guesses -- unlike an existing
            # case, which resolves these from the case lookup step instead.
            messages.error(request, "Choose a court, case category, and case type from the lists to continue.")
        else:
            write_case_data(
                draft,
                {
                    "existing_case": existing_case,
                    "court": court_code,
                    "court_name": request.POST.get("court_name", ""),
                    "case_category": case_category_code,
                    "case_category_name": request.POST.get("case_category_name", ""),
                    "case_type": case_type_code,
                    "case_type_name": request.POST.get("case_type_name", ""),
                    "docket_number": request.POST.get("docket_number", ""),
                },
                current_step=WorkflowStepKey.EXTRACTION_REVIEW,
            )
            _set_lead_filing_type(
                draft,
                request.POST.get("filing_type_code", ""),
                request.POST.get("filing_type_name", ""),
            )
            if request.POST.get("return_to") == RETURN_TO_REVIEW:
                write_case_data(draft, {}, current_step=WorkflowStepKey.REVIEW)
                return redirect(get_step_url(WorkflowStepKey.REVIEW, jurisdiction))
            next_step = get_next_step(WorkflowStepKey.EXTRACTION_REVIEW, draft)
            if next_step:
                write_case_data(draft, {}, current_step=next_step.key)
                return redirect(get_step_url(next_step.key, jurisdiction))

    guesses = draft.extracted_guesses or {}
    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    extraction_context = {
        "jurisdiction": jurisdiction,
        "guesses": guesses,
        "existing_case": draft.existing_case,
        "court_code": draft.court_code,
        "court_name": draft.court_name,
        "case_category_code": draft.case_category_code,
        "case_category_name": draft.case_category_name,
        "case_type_code": draft.case_type_code,
        "case_type_name": draft.case_type_name,
        "filing_type_code": lead.filing_type_code if lead else "",
        "filing_type_name": lead.filing_type_name if lead else "",
    }
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "has_guesses": bool(guesses),
        "docket_number": draft.docket_number or guesses.get("docket number"),
        "extraction_context": extraction_context,
        "return_to": request.GET.get("return_to", ""),
    }
    context.update(get_workflow_context(WorkflowStepKey.EXTRACTION_REVIEW, jurisdiction, draft))
    return render(request, "efile/extraction_review.html", context)
