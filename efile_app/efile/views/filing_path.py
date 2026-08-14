from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, write_case_data
from efile.workflow import ExistingCase, WorkflowStepKey, get_step_url, get_workflow_context


@require_http_methods(["GET", "POST"])
def filing_path(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.FILING_PATH,
        workflow_version=2,
    )

    if request.method == "POST":
        existing_case = request.POST.get("existing_case", "")
        allowed = {choice.value for choice in ExistingCase}
        if existing_case not in allowed:
            messages.error(request, "Choose the option that best describes your filing.")
        else:
            write_case_data(
                draft,
                {"existing_case": existing_case},
                current_step=WorkflowStepKey.UPLOAD_DOCUMENTS,
            )
            return redirect(get_step_url(WorkflowStepKey.UPLOAD_DOCUMENTS, jurisdiction))

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "selected_path": draft.existing_case,
    }
    context.update(get_workflow_context(WorkflowStepKey.FILING_PATH, jurisdiction, draft))
    return render(request, "efile/filing_path.html", context)
