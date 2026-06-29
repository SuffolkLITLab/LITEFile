"""Operations on the durable filing draft aggregate.

This module deliberately has no dependency on HTTP requests, sessions, or the
legacy session data shapes. Request/session selection lives in
``current_drafts``; legacy data translation lives in ``legacy_draft_bridge``.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.workflow import WorkflowStepKey

ACTIVE_DRAFT_STATUSES = (FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR)


def active_drafts_for(user, *, jurisdiction: str | None = None) -> QuerySet[FilingDraft]:
    """Return active drafts owned by ``user``, newest first."""

    drafts = FilingDraft.objects.filter(user=user, status__in=ACTIVE_DRAFT_STATUSES)
    if jurisdiction is not None:
        drafts = drafts.filter(jurisdiction=jurisdiction)
    return drafts.order_by("-updated_at")


def get_active_draft(
    *,
    user,
    draft_id: int | str | None = None,
    jurisdiction: str | None = None,
) -> FilingDraft | None:
    """Get an owned active draft by ID, or the user's most recent draft."""

    drafts = active_drafts_for(user, jurisdiction=jurisdiction)
    if draft_id is not None:
        return drafts.filter(pk=draft_id).first()
    return drafts.first()


@transaction.atomic
def create_draft(
    *,
    user,
    jurisdiction: str,
    current_step: WorkflowStepKey | str = WorkflowStepKey.OPTIONS,
) -> FilingDraft:
    """Create a durable draft owned by an authenticated user."""

    if not getattr(user, "is_authenticated", False):
        raise ValueError("A filing draft must have an authenticated owner")
    if not jurisdiction:
        raise ValueError("A filing draft must have a jurisdiction")

    return FilingDraft.objects.create(
        user=user,
        jurisdiction=jurisdiction,
        current_step=str(current_step),
    )


def set_current_step(draft: FilingDraft, current_step: WorkflowStepKey | str) -> FilingDraft:
    """Advance or rewind a draft's current UI step when it changed."""

    step = str(current_step)
    if draft.current_step != step:
        draft.current_step = step
        draft.save(update_fields=["current_step", "updated_at"])
    return draft


def draft_snapshot(draft: FilingDraft | None) -> dict[str, Any] | None:
    """Return the stable, JSON-safe representation exposed to the UI."""

    if draft is None:
        return None
    return {
        "id": draft.pk,
        "jurisdiction": draft.jurisdiction,
        "status": draft.status,
        "current_step": draft.current_step,
        "existing_case": draft.existing_case,
        "court_code": draft.court_code,
        "court_name": draft.court_name,
        "case_category_code": draft.case_category_code,
        "case_category_name": draft.case_category_name,
        "case_type_code": draft.case_type_code,
        "case_type_name": draft.case_type_name,
        "case_subtype_code": draft.case_subtype_code,
        "case_subtype_name": draft.case_subtype_name,
        "filing_type_code": draft.filing_type_code,
        "filing_type_name": draft.filing_type_name,
        "document_type_code": draft.document_type_code,
        "document_type_name": draft.document_type_name,
        "previous_case_id": draft.previous_case_id,
        "docket_number": draft.docket_number,
        "selected_payment_account_id": draft.selected_payment_account_id,
        "selected_payment_account_name": draft.selected_payment_account_name,
        "optional_services": draft.optional_services,
        "extracted_guesses": draft.extracted_guesses,
        "document_count": FilingDocument.objects.filter(draft=draft).count(),
        "party_count": FilingParty.objects.filter(draft=draft).count(),
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
        "submitted_at": draft.submitted_at.isoformat() if draft.submitted_at else None,
    }
