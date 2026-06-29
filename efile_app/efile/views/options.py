from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import get_current_draft
from efile.services.drafts import draft_snapshot

from ..utils.case_data_utils import get_case_data
from ..workflow import WorkflowStepKey, get_workflow_context


@ensure_csrf_cookie
def efile_options(request, jurisdiction):
    """Options view that displays saved case data and provides next steps."""
    # Get case data from session
    if request.user.is_authenticated:
        case_data = get_case_data(request)
        active_draft = get_current_draft(request, jurisdiction=jurisdiction)
    else:
        case_data = {}
        active_draft = None

    is_logged_in = request.user.is_authenticated
    if not get_tyler_token(request, jurisdiction):
        is_logged_in = False

    # Pass case data to template for display
    context = {
        "is_logged_in": is_logged_in,
        "case_data": case_data,
        "filing_draft": draft_snapshot(active_draft),
        "has_case_data": bool(case_data or active_draft),
    }
    context.update(get_workflow_context(WorkflowStepKey.OPTIONS, jurisdiction))

    return render(request, "efile/options.html", context)
