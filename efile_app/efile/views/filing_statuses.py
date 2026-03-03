from django.shortcuts import redirect, render

from ..utils.case_data_utils import get_case_data


def filing_statuses(request, jurisdiction):
    """Options view that displays saved case data and provides next steps."""
    if not request.user.is_authenticated:
        return redirect("efile_login", jurisdiction=jurisdiction)

    # Get case data from session
    case_data = get_case_data(request)

    # Pass case data to template for display
    context = {
        "case_data": case_data,
        "has_case_data": bool(case_data),
    }

    return render(request, "efile/view_statuses.html", context)
