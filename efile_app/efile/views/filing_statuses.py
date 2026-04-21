from django.shortcuts import redirect, render

from efile.api.suffolk_api_views import get_tyler_token

from ..utils.case_data_utils import get_case_data


def filing_statuses(request, jurisdiction):
    """Options view that displays saved case data and provides next steps."""
    if not request.user.is_authenticated:
        return redirect("efile_login", jurisdiction=jurisdiction)

    # Get case data from session
    case_data = get_case_data(request)

    is_logged_in = request.user.is_authenticated
    if not get_tyler_token(request, jurisdiction):
        is_logged_in = False
    # Pass case data to template for display
    context = {
        "is_logged_in": is_logged_in,
        "case_data": case_data,
        "has_case_data": bool(case_data),
    }

    return render(request, "efile/view_statuses.html", context)
