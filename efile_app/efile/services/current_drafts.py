"""Select the durable filing draft associated with the current request."""

from __future__ import annotations

from django.db import transaction

from efile.models import FilingDraft
from efile.services.drafts import CURRENT_DRAFT_STATUSES, create_draft, get_active_draft, set_current_step
from efile.workflow import WorkflowStepKey

CURRENT_DRAFT_SESSION_KEY = "filing_draft_id"


class DraftIdentityError(Exception):
    """An explicit draft is no longer available for this request."""


def explicit_draft_id(request):
    """Read tab-local identity; never substitute the shared session pointer."""
    values = request.GET.getlist("draft")
    if request.headers.get("X-Filing-Draft") is not None:
        values.append(request.headers["X-Filing-Draft"])
    if request.content_type in {"application/x-www-form-urlencoded", "multipart/form-data"}:
        values.extend(request.POST.getlist("draft"))
    if not values:
        return None
    if len(set(values)) != 1 or not values[0].isascii() or not values[0].isdigit() or len(values[0]) > 18:
        raise DraftIdentityError
    return int(values[0])


def resolve_explicit_draft(request, *, jurisdiction=None, statuses=CURRENT_DRAFT_STATUSES):
    draft_id = explicit_draft_id(request)
    if draft_id is None:
        return None
    user = _authenticated_user(request)
    draft = (
        get_active_draft(user=user, draft_id=draft_id, jurisdiction=jurisdiction, statuses=statuses) if user else None
    )
    if draft is None:
        raise DraftIdentityError
    request.filing_draft = draft
    return draft


def _authenticated_user(request):
    user = getattr(request, "user", None)
    return user if getattr(user, "is_authenticated", False) else None


def attach_current_draft(request, draft: FilingDraft) -> None:
    """Remember which durable draft this browser is editing."""

    request.session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    request.session["jurisdiction"] = draft.jurisdiction
    request.session.modified = True
    request.filing_draft = draft


def clear_current_draft(request) -> None:
    draft = getattr(request, "filing_draft", None)
    if draft is not None and request.session.get(CURRENT_DRAFT_SESSION_KEY) != draft.pk:
        return
    if CURRENT_DRAFT_SESSION_KEY in request.session:
        del request.session[CURRENT_DRAFT_SESSION_KEY]
        request.session.modified = True


def pointed_at_draft(request, *, jurisdiction: str | None = None) -> FilingDraft | None:
    """Resolve the draft this browser says it is editing, or nothing.

    The session only stores a pointer. Ownership, active status, and (when
    supplied) jurisdiction are enforced on every lookup.
    """

    explicit = resolve_explicit_draft(request, jurisdiction=jurisdiction)
    if explicit is not None:
        return explicit
    user = _authenticated_user(request)
    if user is None:
        clear_current_draft(request)
        return None

    draft_id = request.session.get(CURRENT_DRAFT_SESSION_KEY)
    if draft_id is None:
        return None
    try:
        draft_id = int(draft_id)
    except (TypeError, ValueError):
        clear_current_draft(request)
        return None

    # The pointed-at draft may be mid-submission (SUBMITTING); it is still the
    # user's current draft, so resolve it even though resume/listings would not.
    draft = get_active_draft(
        user=user,
        draft_id=draft_id,
        jurisdiction=jurisdiction,
        statuses=CURRENT_DRAFT_STATUSES,
    )
    if draft is None:
        clear_current_draft(request)
    else:
        request.filing_draft = draft
    return draft


def resumable_draft(request, *, jurisdiction: str | None = None) -> FilingDraft | None:
    """The draft a "continue where you left off" offer would resume.

    Read-only, deliberately: finding a draft is not the same as deciding the
    filer is working on it. See ``adopt_draft``.
    """

    user = _authenticated_user(request)
    if user is None:
        return None
    return get_active_draft(user=user, jurisdiction=jurisdiction)


def adopt_draft(request, draft_id, *, jurisdiction: str | None = None) -> FilingDraft | None:
    """Make an owned draft the current one, at the filer's explicit request."""

    user = _authenticated_user(request)
    if user is None or draft_id in (None, ""):
        return None
    try:
        draft_id = int(draft_id)
    except (TypeError, ValueError):
        return None
    draft = get_active_draft(
        user=user,
        draft_id=draft_id,
        jurisdiction=jurisdiction,
        statuses=CURRENT_DRAFT_STATUSES,
    )
    if draft is not None:
        attach_current_draft(request, draft)
    return draft


def get_current_draft(
    request,
    *,
    jurisdiction: str | None = None,
    resume_latest: bool = False,
) -> FilingDraft | None:
    """Resolve a named draft, falling back only to this session's own pointer.

    Only resume offers opt into finding the account's latest draft. APIs must
    not read a filing just because another browser recently worked on it.
    """

    draft = pointed_at_draft(request, jurisdiction=jurisdiction)
    if draft is not None or not resume_latest:
        return draft
    return resumable_draft(request, jurisdiction=jurisdiction)


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


RESUME_DRAFT_PARAM = "draft"


@transaction.atomic
def ensure_current_draft(
    request,
    jurisdiction: str,
    *,
    current_step: WorkflowStepKey | str | None = None,
    workflow_version: int | None = None,
) -> FilingDraft:
    """Return the draft this screen is for, creating a blank one if there is none.

    A workflow screen works on the draft the browser is pointing at, or on the
    one the filer named by resuming it. It never reaches for the newest filing
    lying around: someone starting a filing gets an empty one, not the documents
    from a matter they finished last month.
    """

    # A named draft belongs to this request. Resolving it must not replace the
    # shared session pointer, and an invalid identity must never fall through.
    draft = pointed_at_draft(request, jurisdiction=jurisdiction)
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
