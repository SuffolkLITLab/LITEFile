import logging

from django.shortcuts import redirect, render

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot

from ..utils.case_data_utils import get_upload_data
from ..workflow import WorkflowStepKey, get_workflow_context

logger = logging.getLogger(__name__)


def efile_expert_form(request, jurisdiction):
    """Expert form view for creating filings with cascading dropdowns."""
    # Log all GET parameters for debugging
    logger.debug(f"Expert form accessed with GET parameters: {dict(request.GET)}")

    if not request.user.is_authenticated:
        return redirect("efile_login", jurisdiction=jurisdiction)

    filing_draft = ensure_current_draft(request, jurisdiction, current_step=WorkflowStepKey.CASE_INFORMATION)

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
    logger.debug(f"All session data keys: {list(request.session.keys())}")
    logger.debug(f"Clear session parameter received: {request.GET.get('clear_session', 'not present')}")

    upload_data = get_upload_data(request)

    # Check if we have all required data for upload
    required_fields = ["court", "case_category", "case_type", "filing_type", "document_type"]
    has_all_required = all(case_data.get(field) for field in required_fields)

    # For name change cases, also check for party information
    has_party_info = True  # Default for non-name change cases
    if has_all_required and "name change" in case_data.get("case_type", "").lower():
        party_fields = ["petitioner_first_name", "petitioner_last_name", "new_first_name", "new_last_name"]
        has_party_info = all(case_data.get(field) for field in party_fields)

    is_logged_in = request.user.is_authenticated
    if not get_tyler_token(request, jurisdiction):
        is_logged_in = False
    # Display the form for data collection with existing data populated
    context = {
        "is_logged_in": is_logged_in,
        "case_data": case_data,
        "filing_draft": draft_snapshot(filing_draft),
        "guessed_court": upload_data.get("guesses", {}).get("court"),
        "guessed_case_category": upload_data.get("guesses", {}).get("case type"),
        "guessed_case_type": upload_data.get("guesses", {}).get("case category"),
        "auth_tokens": auth_tokens,
        "can_proceed_to_upload": has_all_required and has_party_info,
        "missing_required_fields": not has_all_required,
        "missing_party_info": has_all_required and not has_party_info,
    }
    context.update(get_workflow_context(WorkflowStepKey.CASE_INFORMATION, jurisdiction))

    return render(request, "efile/expert_form.html", context)
