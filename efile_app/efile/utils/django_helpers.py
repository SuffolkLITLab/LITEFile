"""
Helpers for shared django functions used throughout
"""

import logging

logger = logging.getLogger(__name__)

_FILING_SESSION_KEYS = {
    "case_data",
    "existing_case",
    "filing_draft_id",
    "jurisdiction",
    "last_submitted_filing_draft_id",
    "session_id",
    "upload_data",
}


def flush_cache_stay_logged_in(session):
    """Discard filing state without rotating the authenticated session.

    ``session.flush()`` deletes the session and creates a new key. On the options
    page that can race with its in-flight draft lookup, leaving the newly created
    draft attached to a session that Django no longer recognizes as logged in.
    Filing state has a small, explicit namespace, so remove only those keys.
    """
    removed = [key for key in _FILING_SESSION_KEYS if key in session]
    for key in removed:
        del session[key]
    session.modified = True
    logger.debug("Cleared filing session keys: %s", sorted(removed))
