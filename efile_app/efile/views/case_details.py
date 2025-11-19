"""
Case details view for handling existing case responses
"""

import logging

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def case_details(request, jurisdiction):
    """
    Display the case details form for existing case responses
    """
    try:
        # Check if we need to clear cache (only when explicitly coming from options page button)
        clear_cache = request.GET.get("clear_cache", "false").lower() == "true"
        from_options = request.GET.get("from_options", "false").lower() == "true"

        logger.debug(
            f"Case details - Cache clear conditions - clear_cache: {clear_cache}, from_options: {from_options}"
        )

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

            logger.debug(
                "FULL cache cleared from case details via options page - session keys after clear: %s",
                list(request.session.keys()),
            )
        else:
            logger.debug("Cache NOT cleared - preserving existing session data")

        # Get jurisdiction config (can be expanded later for other jurisdictions)
        return render(request, "efile/case_details.html")

    except Exception as e:
        logger.error(f"Error loading case details page: {str(e)}")
        return render(request, "efile/case_details.html", {"error": "An error occurred loading the page"})
