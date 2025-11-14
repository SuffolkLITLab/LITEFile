from django.shortcuts import render

from efile.utils.config_loader import config_loader
from ..utils.case_data_utils import get_case_data


def efile_options(request, jurisdiction):
    """Options view that displays saved case data and provides next steps."""

    # Get case data from session
    case_data = get_case_data(request)

    # Pass case data to template for display
    jurisdiction_config = config_loader.get_short_jurisdiction_config(jurisdiction)
    context = {"case_data": case_data, "has_case_data": bool(case_data), "jurisdiction": jurisdiction, "jurisdiction_config": jurisdiction_config}

    return render(request, "efile/options.html", context)
