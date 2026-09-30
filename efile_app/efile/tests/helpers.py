"""Shared helpers for tests that drive the submit path."""

from efile.services.disclaimers import disclaimer_context


def accepted_submission(draft, **fields):
    """A submit body that accepts the court requirements shown on Review for this draft."""
    return {
        "disclaimer_token": disclaimer_context(draft)["disclaimer_token"],
        "confirm_submission": True,
        **fields,
    }
