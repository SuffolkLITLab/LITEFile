from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, write_case_data
from efile.services.filing_plans import link_case_to_plan, remember_case_for_plan
from efile.workflow import ExistingCase, WorkflowStepKey, get_step_url, get_workflow_context


@require_http_methods(["GET", "POST"])
def case_confirmation(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.CASE_CONFIRMATION,
        workflow_version=2,
    )
    if draft.existing_case != ExistingCase.EXISTING:
        return redirect("document_checklist", jurisdiction=jurisdiction)
    if not draft.previous_case_id or not draft.docket_number:
        messages.error(request, "Find your court case before confirming it.")
        return redirect("case_lookup", jurisdiction=jurisdiction)

    if request.method == "POST":
        if request.POST.get("confirmed") == "yes":
            # The filer has just told us which court case this matter is. Keep
            # it on the plan so their next filing goes into the same case
            # without searching for it again.
            remember_case_for_plan(draft)
            draft.current_step = WorkflowStepKey.DOCUMENT_CHECKLIST
            draft.save(update_fields=["current_step", "updated_at"])
            return redirect(get_step_url(WorkflowStepKey.DOCUMENT_CHECKLIST, jurisdiction))

        # Saying "this is not my case" about the case the plan proposed means
        # the plan is pointing at the wrong one, so it stops pointing anywhere.
        if draft.plan is not None and draft.plan.case_tracking_id == draft.previous_case_id:
            link_case_to_plan(draft.plan, case_tracking_id="", docket_number="", case_title="")

        write_case_data(
            draft,
            {
                "previous_case_id": "",
                "docket_number": "",
                "case_title": "",
                "case_category_code": "",
                "case_category_name": "",
                "case_type_code": "",
                "case_type_name": "",
            },
            current_step=WorkflowStepKey.CASE_LOOKUP,
        )
        return redirect(get_step_url(WorkflowStepKey.CASE_LOOKUP, jurisdiction))

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "case": draft,
    }
    context.update(get_workflow_context(WorkflowStepKey.CASE_CONFIRMATION, jurisdiction, draft))
    return render(request, "efile/case_confirmation.html", context)
