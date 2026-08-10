"""Select the durable filing draft associated with the current request."""

from __future__ import annotations

from django.db import transaction

from efile.models import FilingDraft
from efile.services.drafts import CURRENT_DRAFT_STATUSES, create_draft, get_active_draft, set_current_step
from efile.workflow import WorkflowStepKey

CURRENT_DRAFT_SESSION_KEY = "filing_draft_id"


def _authenticated_user(request):
    user = getattr(request, "user", None)
    return user if getattr(user, "is_authenticated", False) else None


def attach_current_draft(request, draft: FilingDraft) -> None:
    """Remember which durable draft this browser is editing."""

    request.session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    request.session["jurisdiction"] = draft.jurisdiction
    request.session.modified = True


def clear_current_draft(request) -> None:
    if CURRENT_DRAFT_SESSION_KEY in request.session:
        del request.session[CURRENT_DRAFT_SESSION_KEY]
        request.session.modified = True


def get_current_draft(
    request,
    *,
    jurisdiction: str | None = None,
    resume_latest: bool = True,
) -> FilingDraft | None:
    """Resolve the current user's draft without trusting a bare session ID.

    The session only stores a pointer. Ownership, active status, and (when
    supplied) jurisdiction are enforced on every lookup.
    """

    user = _authenticated_user(request)
    if user is None:
        clear_current_draft(request)
        return None

    draft_id = request.session.get(CURRENT_DRAFT_SESSION_KEY)
    if draft_id is not None:
        try:
            draft_id = int(draft_id)
        except (TypeError, ValueError):
            clear_current_draft(request)
            draft_id = None

    if draft_id is not None:
        # The pointed-at draft may be mid-submission (SUBMITTING); it is still the
        # user's current draft, so resolve it even though resume/listings would not.
        draft = get_active_draft(
            user=user,
            draft_id=draft_id,
            jurisdiction=jurisdiction,
            statuses=CURRENT_DRAFT_STATUSES,
        )
        if draft is not None:
            return draft
        clear_current_draft(request)

    if not resume_latest:
        return None

    draft = get_active_draft(user=user, jurisdiction=jurisdiction)
    if draft is not None:
        attach_current_draft(request, draft)
    return draft


@transaction.atomic
def create_current_draft(
    request,
    jurisdiction: str,
    *,
    current_step: WorkflowStepKey | str = WorkflowStepKey.OPTIONS,
    workflow_version: int = 2,
) -> FilingDraft:
    draft = create_draft(
        user=_authenticated_user(request),
        jurisdiction=jurisdiction,
        current_step=current_step,
        workflow_version=workflow_version,
    )
    attach_current_draft(request, draft)
    return draft


@transaction.atomic
def ensure_current_draft(
    request,
    jurisdiction: str,
    *,
    current_step: WorkflowStepKey | str | None = None,
    workflow_version: int | None = None,
) -> FilingDraft:
    draft = get_current_draft(request, jurisdiction=jurisdiction)
    if draft is None:
        return create_current_draft(
            request,
            jurisdiction,
            current_step=current_step or WorkflowStepKey.OPTIONS,
            workflow_version=workflow_version or 2,
        )
    if current_step is not None:
        set_current_step(draft, current_step)
    if workflow_version is not None and draft.workflow_version != workflow_version:
        draft.workflow_version = workflow_version
        draft.save(update_fields=["workflow_version", "updated_at"])
    return draft
