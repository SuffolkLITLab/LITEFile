from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, write_case_data
from efile.workflow import (
    ExistingCase,
    WorkflowStepKey,
    get_next_step,
    get_step_url,
    get_workflow_context,
)


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
        if existing_case not in {ExistingCase.NEW, ExistingCase.EXISTING}:
            messages.error(request, "Choose whether this is a new or existing court case to continue.")
        else:
            write_case_data(
                draft,
                {
                    "existing_case": existing_case,
                    "court_name": request.POST.get("court_name", ""),
                    "case_category_name": request.POST.get("case_category_name", ""),
                    "case_type_name": request.POST.get("case_type_name", ""),
                    "docket_number": request.POST.get("docket_number", ""),
                },
                current_step=WorkflowStepKey.EXTRACTION_REVIEW,
            )
            next_step = get_next_step(WorkflowStepKey.EXTRACTION_REVIEW, draft)
            if next_step:
                write_case_data(draft, {}, current_step=next_step.key)
                return redirect(get_step_url(next_step.key, jurisdiction))

    guesses = draft.extracted_guesses or {}
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "guesses": guesses,
        "court_name": draft.court_name or guesses.get("court"),
        "case_category_name": draft.case_category_name or guesses.get("case category"),
        "case_type_name": draft.case_type_name or guesses.get("case type"),
        "docket_number": draft.docket_number or guesses.get("docket number"),
    }
    context.update(get_workflow_context(WorkflowStepKey.EXTRACTION_REVIEW, jurisdiction, draft))
    return render(request, "efile/extraction_review.html", context)
