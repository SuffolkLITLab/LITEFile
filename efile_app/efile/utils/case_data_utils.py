"""Accessors for the current filing's case/upload data.

The durable ``FilingDraft`` aggregate is the single source of truth. These
helpers keep their old ``request``-based signatures so every view, template, and
the submission path keep working, but they now (de)serialize the draft instead of
reading a session blob. The browser still exchanges the same flat JSON shape;
only the server-side store moved.
"""

import logging

from efile.services.current_drafts import ensure_current_draft, get_current_draft
from efile.services.drafts import read_case_data, read_upload_data, write_case_data, write_upload_data

logger = logging.getLogger(__name__)


def _current_jurisdiction(request):
    draft = get_current_draft(request, resume_latest=False)
    if draft is not None:
        return draft.jurisdiction
    return request.session.get("jurisdiction")


def _resolve_writable_draft(request, jurisdiction=None):
    """Return the draft to write to, creating one for authenticated users only.

    When ``jurisdiction`` is given (the route/payload the caller is acting on), it
    is enforced so a request for jurisdiction A can never write jurisdiction B's
    currently-pointed draft.
    """
    if not getattr(request.user, "is_authenticated", False):
        return None
    target = jurisdiction or _current_jurisdiction(request)
    if target:
        return ensure_current_draft(request, target)
    return get_current_draft(request)


def get_case_data(request, jurisdiction=None):
    """Return the current draft serialized to the case_data blob (``{}`` if none).

    Passing ``jurisdiction`` (the route the caller is serving) enforces isolation:
    a draft pointed to from a different jurisdiction is not returned.
    """
    return read_case_data(get_current_draft(request, jurisdiction=jurisdiction))


def update_case_data(request, updates, jurisdiction=None):
    """Persist a partial case_data blob onto the current draft and return the merged blob."""
    draft = _resolve_writable_draft(request, jurisdiction)
    if draft is None:
        return {}
    write_case_data(draft, updates)
    return read_case_data(draft)


def get_upload_data(request, jurisdiction=None):
    return read_upload_data(get_current_draft(request, jurisdiction=jurisdiction))


def update_upload_data(request, updates, jurisdiction=None):
    draft = _resolve_writable_draft(request, jurisdiction)
    if draft is None:
        return {}
    write_upload_data(draft, updates)
    return read_upload_data(draft)


def get_petitioner_info(request, jurisdiction=None):
    """Get petitioner information specifically."""
    case_data = get_case_data(request, jurisdiction)
    full_name = f"{case_data.get('petitioner_first_name', '')} {case_data.get('petitioner_last_name', '')}".strip()
    return {
        "first_name": case_data.get("petitioner_first_name", ""),
        "last_name": case_data.get("petitioner_last_name", ""),
        "address": case_data.get("petitioner_address", ""),
        "full_name": full_name,
    }


def get_name_sought_info(request, jurisdiction=None):
    """Get name sought information specifically."""
    case_data = get_case_data(request, jurisdiction)
    return {
        "first_name": case_data.get("new_first_name", ""),
        "last_name": case_data.get("new_last_name", ""),
        "full_name": f"{case_data.get('new_first_name', '')} {case_data.get('new_last_name', '')}".strip(),
    }


def get_case_classification(request, jurisdiction=None):
    """Get case classification information."""
    case_data = get_case_data(request, jurisdiction)
    logger.info("Case data: %s", case_data)
    return {
        "court": case_data.get("court", ""),
        "case_category": case_data.get("case_category", ""),
        "case_type": case_data.get("case_type", ""),
        "filing_type": case_data.get("filing_type", ""),
        "document_type": case_data.get("document_type", ""),
        "is_name_change": "name change" in case_data.get("case_type", "").lower(),
    }


def get_selected_services(request, jurisdiction=None):
    """Get list of selected optional services."""
    case_data = get_case_data(request, jurisdiction)
    return case_data.get("optional_services", [])
