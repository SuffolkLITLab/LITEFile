import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from ..utils.case_data_utils import get_case_classification, get_case_data, get_name_sought_info, get_petitioner_info

logger = logging.getLogger(__name__)


def case_review(request, jurisdiction):
    """Review view for case details before final submission."""

    # Get case data from session
    case_data = get_case_data(request)
    logger.debug("Review view case_data %s", case_data)

    # Add user email from session if available and not already in case_data
    user_email = request.session.get("user_email")
    if user_email and not case_data.get("email"):
        case_data["email"] = user_email

    # If no case data exists, redirect back to expert form
    if not case_data:
        messages.error(request, "Please complete the case details first.")
        return redirect("expert_form", jurisdiction=jurisdiction)

    # Get organized case information
    petitioner_info = get_petitioner_info(request)
    name_sought_info = get_name_sought_info(request)
    case_classification = get_case_classification(request)

    # Use friendly names if available, otherwise fallback to raw values
    friendly_case_type = case_data.get("case_type_name", case_classification["case_type"])
    friendly_filing_type = case_data.get("filing_type_name", case_classification["filing_type"])
    friendly_court = case_data.get("court_name", case_classification["court"])
    friendly_case_category = case_data.get("case_category_name", case_classification.get("case_category", ""))
    friendly_document_type = case_data.get("document_type_name", case_classification.get("document_type", ""))

    # Organize data for review
    review_sections = {
        "case_classification": {
            "title": "Case Classification",
            "items": [
                {"label": "County/Court", "value": friendly_court, "raw": case_classification["court"]},
                {
                    "label": "Case Category",
                    "value": friendly_case_category,
                    "raw": case_classification.get("case_category", ""),
                },
                {"label": "Case Type", "value": friendly_case_type, "raw": case_classification["case_type"]},
                {"label": "Filing Type", "value": friendly_filing_type, "raw": case_classification["filing_type"]},
                {
                    "label": "Document Type",
                    "value": friendly_document_type,
                    "raw": case_classification.get("document_type", ""),
                },
            ],
        },
        "petitioner_info": {
            "title": "Petitioner Information",
            "items": [
                {"label": "First Name", "value": petitioner_info.get("first_name", "")},
                {"label": "Last Name", "value": petitioner_info.get("last_name", "")},
                {"label": "Address", "value": petitioner_info.get("address", "")},
                {"label": "City", "value": petitioner_info.get("city", "")},
                {"label": "State", "value": petitioner_info.get("state", "")},
                {"label": "Zip Code", "value": petitioner_info.get("zip_code", "")},
                {"label": "Phone", "value": petitioner_info.get("phone", "")},
                {"label": "Email", "value": petitioner_info.get("email", "")},
            ],
        },
    }

    # Add name sought info if it's a name change case
    if "name change" in friendly_case_type.lower():
        review_sections["name_sought"] = {
            "title": "Name Change Details",
            "items": [
                {"label": "First Name", "value": name_sought_info.get("first_name", "")},
                {"label": "Last Name", "value": name_sought_info.get("last_name", "")},
                {"label": "Reason for Change", "value": case_data.get("reason_for_name_change", "")},
            ],
        }

    # Add optional services if any
    optional_services = case_data.get("optional_services", [])
    if optional_services:
        review_sections["optional_services"] = {
            "title": "Optional Services",
            "items": [{"label": "Selected Services", "value": ", ".join(optional_services)}],
        }

    new_toga_url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/payments/new-toga-account"

    context = {
        "new_toga_url": new_toga_url,
        "case_data": case_data,
        "review_sections": review_sections,
        "friendly_names": {
            "case_type": friendly_case_type,
            "filing_type": friendly_filing_type,
            "court": friendly_court,
            "case_category": friendly_case_category,
            "document_type": friendly_document_type,
        },
    }

    return render(request, "efile/review.html", context)
