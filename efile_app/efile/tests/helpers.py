"""Shared helpers for tests that drive the submit path."""

from efile.services.disclaimers import disclaimer_context


def accepted_submission(draft, **fields):
    """A submit body that accepts the court requirements shown on Review for this draft."""
    return {
        "disclaimer_token": disclaimer_context(draft)["disclaimer_token"],
        "confirm_submission": True,
        **fields,
    }


def reviewed_document(**fields):
    """A previously prepared and acknowledged document for downstream flow tests."""
    from django.utils import timezone

    from efile.models import FilingDocument

    fields.setdefault("preparation", "unchanged")
    fields.setdefault("preparation_reviewed_at", timezone.now())
    return FilingDocument.objects.create(**fields)


def loaded_case_snapshot(draft, *, confirmed=True):
    """A trusted empty court response for tests of routing rather than import."""
    from django.conf import settings

    return {
        "schema_version": 1,
        "status": "loaded",
        "confirmed": confirmed,
        "court": draft.court_code,
        "tracking_id": draft.previous_case_id,
        "source_environment": settings.EFSP_URL,
        "parties": [],
        "problems": [],
        "docket_number": draft.docket_number,
        "case_title": draft.case_title,
        "case_category_code": draft.case_category_code,
        "case_type_code": draft.case_type_code,
    }
