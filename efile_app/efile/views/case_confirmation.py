from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingParty
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, write_case_data
from efile.services.existing_cases import (
    CaseImportError,
    confirm_case,
    import_ready,
    load_case,
    reusable_snapshot,
)
from efile.services.filing_availability import draft_unavailable_message, unavailable_response
from efile.services.filing_plans import link_case_to_plan, remember_case_for_plan
from efile.workflow import (
    ExistingCase,
    WorkflowStepKey,
    continue_step,
    continue_url,
    get_step_url,
    get_workflow_context,
    return_target,
    with_return_to,
)


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

    availability_message = draft_unavailable_message(draft)
    confirming = request.method == "POST" and request.POST.get("confirmed") == "yes"
    if availability_message and confirming:
        return unavailable_response(request, draft, availability_message)

    import_error = ""
    if not availability_message and (request.method == "GET" or confirming):
        # Reuse a recent preview rather than asking the court again on every
        # reload; "Yes" on a partial or failed import is the Retry button.
        retrying = confirming and draft.existing_case_snapshot.get("status") != "loaded"
        if not import_ready(draft) and (retrying or not reusable_snapshot(draft)):
            try:
                load_case(draft, get_tyler_token(request, jurisdiction))
            except CaseImportError as error:
                import_error = str(error)
        if draft.existing_case_snapshot.get("status") == "partial":
            import_error = (
                " ".join(draft.existing_case_snapshot.get("problems", []))
                + " Retry loading the case or contact support."
            )

    if request.method == "POST":
        if confirming and not import_error:
            try:
                confirm_case(draft)
            except CaseImportError as error:
                messages.error(request, str(error))
                return redirect("case_confirmation", jurisdiction=jurisdiction)
            if message := draft_unavailable_message(draft):
                return unavailable_response(request, draft, message)
            # The filer has just told us which court case this matter is. Keep
            # it on the plan so their next filing goes into the same case
            # without searching for it again.
            remember_case_for_plan(draft)
            return_to = return_target(request)
            draft.current_step = continue_step(draft, return_to, WorkflowStepKey.DOCUMENT_CHECKLIST)
            draft.save(update_fields=["current_step", "updated_at"])
            return redirect(continue_url(draft, jurisdiction, return_to, WorkflowStepKey.DOCUMENT_CHECKLIST))

        if confirming:
            return _render(request, jurisdiction, draft, import_error, availability_message, status=422)

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
        return redirect(with_return_to(get_step_url(WorkflowStepKey.CASE_LOOKUP, jurisdiction), return_target(request)))

    return _render(request, jurisdiction, draft, import_error, availability_message)


def _render(request, jurisdiction, draft, import_error, availability_message, status=200):
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "case": draft,
        "import_error": import_error,
        "court_parties": [FilingParty(**party) for party in draft.existing_case_snapshot.get("parties", [])],
        "availability_message": availability_message,
        "return_to": return_target(request),
    }
    context.update(get_workflow_context(WorkflowStepKey.CASE_CONFIRMATION, jurisdiction, draft))
    return render(request, "efile/case_confirmation.html", context, status=status)
