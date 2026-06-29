from django.shortcuts import render

from efile.api.suffolk_api_views import get_tyler_token

from ..utils.case_data_utils import get_case_data
from ..workflow import get_workflow_context


def efile_options(request, jurisdiction):
    """Options view that displays saved case data and provides next steps."""
    # Get case data from session
    if request.user.is_authenticated:
        case_data = get_case_data(request)
    else:
        case_data = {}

    is_logged_in = request.user.is_authenticated
    if not get_tyler_token(request, jurisdiction):
        is_logged_in = False

    # Pass case data to template for display
    context = {
        "is_logged_in": is_logged_in,
        "case_data": case_data,
        "has_case_data": bool(case_data),
    }
    context.update(get_workflow_context("options", jurisdiction))

    return render(request, "efile/options.html", context)
