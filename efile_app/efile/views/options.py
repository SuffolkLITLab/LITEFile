from django.shortcuts import render

from ..utils.case_data_utils import get_case_data


def efile_options(request):
    """Options view that displays saved case data and provides next steps."""

    # Get case data from session
    case_data = get_case_data(request)

    # Pass case data to template for display
    context = {"case_data": case_data, "has_case_data": bool(case_data)}

    return render(request, "efile/options.html", context)
