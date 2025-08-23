import logging

from django.shortcuts import render

logger = logging.getLogger(__name__)


def efile_expert_form(request):
    """Expert form view for creating filings with cascading dropdowns."""
    # Get auth tokens from session if available
    auth_tokens = request.session.get("auth_tokens", None)
    # Log only presence/keys, not token values
    if auth_tokens:
        logger.debug("Auth tokens present with keys=%s", list(auth_tokens.keys()))
    else:
        logger.debug("No auth tokens in session")

    # Get existing case data from session to populate form
    case_data = request.session.get("case_data", {})

    logger.debug(f"Case data from session: {case_data}")

    # Check if we have all required data for upload
    required_fields = ["court", "case_category", "case_type", "filing_type", "document_type"]
    has_all_required = all(case_data.get(field) for field in required_fields)

    # For name change cases, also check for party information
    has_party_info = True  # Default for non-name change cases
    if has_all_required and "name change" in case_data.get("case_type", "").lower():
        party_fields = ["petitioner_first_name", "petitioner_last_name", "new_first_name", "new_last_name"]
        has_party_info = all(case_data.get(field) for field in party_fields)

    # Display the form for data collection with existing data populated
    context = {
        "case_data": case_data,
        "auth_tokens": auth_tokens,
        "can_proceed_to_upload": has_all_required and has_party_info,
        "missing_required_fields": not has_all_required,
        "missing_party_info": has_all_required and not has_party_info,
    }

    return render(request, "efile/expert_form.html", context)
