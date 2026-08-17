import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, write_case_data
from efile.workflow import ExistingCase, WorkflowStepKey, get_step_url, get_workflow_context


@require_http_methods(["GET", "POST"])
def case_lookup(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.CASE_LOOKUP,
        workflow_version=2,
    )
    if draft.existing_case != ExistingCase.EXISTING:
        messages.info(request, "Case lookup is only needed for an existing court case.")
        return redirect("document_checklist", jurisdiction=jurisdiction)
    if request.method == "GET" and draft.previous_case_id and draft.docket_number:
        # The case is already known -- usually because this filing came from a
        # plan that files into it. Searching for a case we have is busywork;
        # the confirm step is where the filer says whether it is the right one,
        # and answering no there comes back here with the case cleared.
        return redirect(get_step_url(WorkflowStepKey.CASE_CONFIRMATION, jurisdiction))

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid case information."}, status=400)

        court_code = data.get("court")
        docket_number = data.get("case_docket_id") or data.get("docket_number")
        tracking_id = data.get("case_tracking_id")
        if not court_code or not docket_number or not tracking_id:
            return JsonResponse(
                {"success": False, "error": "The case lookup result is missing required information."},
                status=400,
            )

        write_case_data(
            draft,
            {
                "existing_case": ExistingCase.EXISTING,
                "court": court_code,
                "court_name": data.get("court_name", ""),
                "case_tracking_id": tracking_id,
                "case_docket_id": docket_number,
                "case_title": data.get("case_title", ""),
                "case_category_code": data.get("case_category_code", ""),
                "case_category_name": data.get("case_category_name", ""),
                "case_type_code": data.get("case_type_code", ""),
                "case_type_name": data.get("case_type_name", ""),
            },
            current_step=WorkflowStepKey.CASE_CONFIRMATION,
        )
        return JsonResponse(
            {
                "success": True,
                "redirect_url": get_step_url(WorkflowStepKey.CASE_CONFIRMATION, jurisdiction),
            }
        )

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "guessed_court": draft.court_name or (draft.extracted_guesses or {}).get("court", ""),
        "selected_court_code": draft.court_code,
        "docket_number": draft.docket_number or (draft.extracted_guesses or {}).get("docket number", ""),
    }
    context.update(get_workflow_context(WorkflowStepKey.CASE_LOOKUP, jurisdiction, draft))
    return render(request, "efile/case_lookup.html", context)
