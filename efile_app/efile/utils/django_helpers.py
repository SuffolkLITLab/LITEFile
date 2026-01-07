"""
Helpers for shared django functions used throughout
"""

import logging

logger = logging.getLogger(__name__)


def flush_cache_stay_logged_in(session):
    # Store auth info before clearing everything
    to_save = {
        k: session.get(k, None)
        for k in ["auth_tokens", "user_email", "_auth_user_id", "_auth_user_backend", "_auth_user_hash"]
    }

    logger.debug("Before cache clear - session keys: %s", list(session.keys()))
    logger.debug(
        "session: %s",
        session,
    )

    # Clear ALL session data
    session.flush()

    for key, value in to_save.items():
        if value:
            session[key] = value

    # Force session to save changes
    session.modified = True

    logger.debug(
        "FULL cache cleared from expert form via options page - session keys after clear: %s",
        list(session.keys()),
    )
    logger.debug(
        "session: %s",
        session,
    )
