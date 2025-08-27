import logging

from django.shortcuts import render

logger = logging.getLogger(__name__)


def efile_expert_form(request):
    """Expert form view for creating filings with cascading dropdowns."""
    # Log all GET parameters for debugging
    logger.debug(f"Expert form accessed with GET parameters: {dict(request.GET)}")
    
    # Check if we need to clear cache (only when explicitly coming from options page button)
    clear_cache = request.GET.get("clear_cache", "false").lower() == "true"
    from_options = request.GET.get("from_options", "false").lower() == "true"
    
    logger.debug(f"Cache clear conditions - clear_cache: {clear_cache}, from_options: {from_options}")
    
    # Only clear cache if both conditions are met: clear_cache=true AND from_options=true
    if clear_cache and from_options:
        # Store auth info before clearing everything
        auth_tokens = request.session.get("auth_tokens", None)
        user_email = request.session.get("user_email", None)
        
        logger.debug("Before cache clear - session keys: %s", list(request.session.keys()))
        
        # Clear ALL session data
        request.session.flush()
        
        # Restore only essential auth info
        if auth_tokens:
            request.session["auth_tokens"] = auth_tokens
        if user_email:
            request.session["user_email"] = user_email
        
        # Force session to save changes
        request.session.modified = True
            
        logger.debug("FULL cache cleared from expert form via options page - session keys after clear: %s", list(request.session.keys()))
    else:
        logger.debug("Cache NOT cleared - preserving existing session data")
    
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
    logger.debug(f"Clear cache parameter received: {request.GET.get('clear_cache', 'not present')}")

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
