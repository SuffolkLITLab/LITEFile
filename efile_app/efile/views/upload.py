import logging

from django.contrib import messages
from django.shortcuts import redirect, render

from ..utils.case_data_utils import (
    get_case_classification,
    get_case_data,
    get_name_sought_info,
    get_petitioner_info,
    get_upload_data,
)

logger = logging.getLogger(__name__)


def efile_upload(request, jurisdiction):
    """Upload view for document submission and filing creation."""

    # Check if user is authenticated first
    if not request.user.is_authenticated:
        return redirect("efile_login", jurisdiction=jurisdiction)

    # Get case data from session
    case_data = get_case_data(request)

    # If no case data exists, redirect back to options page
    if not case_data:
        messages.error(request, "Please complete the case details first.")
        return redirect("efile_options", jurisdiction=jurisdiction)

    # Get organized case information
    petitioner_info = get_petitioner_info(request)
    name_sought_info = get_name_sought_info(request)
    case_classification = get_case_classification(request)

    # Use friendly names if available, otherwise fallback to raw values
    friendly_case_type = case_data.get("case_type_name", case_classification["case_type"])
    friendly_filing_type = case_data.get("filing_type_name", case_classification["filing_type"])
    friendly_court = case_data.get("court_name", case_classification["court"])

    upload_data = get_upload_data(request)

    context = {
        "case_data": case_data,
        "upload_data": upload_data,
        "petitioner_info": petitioner_info,
        "name_sought_info": name_sought_info,
        "case_classification": case_classification,
        "case_type_name": friendly_case_type,
        "filing_type": friendly_filing_type,
        "court": friendly_court,
        "case_type_raw": case_classification["case_type"],
        "category_type_raw": case_classification["case_category"],
        "filing_type_raw": case_classification["filing_type"],
        "court_raw": case_classification["court"],
    }

    return render(request, "efile/upload.html", context)
