from django.shortcuts import render

from ..utils.case_data_utils import get_case_data


def efile_options(request, jurisdiction):
    """Options view that displays saved case data and provides next steps."""
    # Get case data from session
    if request.user.is_authenticated:
        case_data = get_case_data(request)
    else:
        case_data = {}

    # Pass case data to template for display
    context = {
        "is_logged_in": request.user.is_authenticated,
        "case_data": case_data,
        "has_case_data": bool(case_data),
    }

    return render(request, "efile/options.html", context)
