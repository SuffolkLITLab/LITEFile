from django.middleware.csrf import get_token
from django.shortcuts import render

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import get_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.filing_plans import plans_for

from ..utils.case_data_utils import get_case_data
from ..workflow import WorkflowStepKey, get_resume_step_url, get_workflow_context


def efile_options(request, jurisdiction):
    """Options view that displays saved case data and provides next steps."""
    get_token(request)

    # Get case data from session
    if request.user.is_authenticated:
        case_data = get_case_data(request, jurisdiction)
        active_draft = get_current_draft(request, jurisdiction=jurisdiction)
        plans = plans_for(request.user, jurisdiction)
    else:
        case_data = {}
        active_draft = None
        plans = []

    is_logged_in = request.user.is_authenticated
    if not get_tyler_token(request, jurisdiction):
        is_logged_in = False

    # Pass case data to template for display
    context = {
        "is_logged_in": is_logged_in,
        "case_data": case_data,
        "filing_draft": draft_snapshot(active_draft),
        "resume_url": get_resume_step_url(
            active_draft.current_step if active_draft else None,
            jurisdiction,
            draft_id=active_draft.pk if active_draft else None,
        ),
        "has_case_data": bool(case_data or active_draft),
        # The three most recently worked on matters. The rest are one click
        # further on, rather than turning this page into a list of everything.
        "plans": plans[:3],
        "plan_count": len(plans),
    }
    context.update(get_workflow_context(WorkflowStepKey.OPTIONS, jurisdiction, active_draft))

    return render(request, "efile/options.html", context)
