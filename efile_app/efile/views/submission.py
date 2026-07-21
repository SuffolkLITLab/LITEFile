import json
import logging
from datetime import timedelta

from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from efile.models import FilingDraft
from efile.services.current_drafts import clear_current_draft, get_current_draft

from .session_api import submit_final_filing as legacy_submit_final_filing

logger = logging.getLogger(__name__)

_CLAIMABLE_STATUSES = (FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR)

# A claim older than this is assumed to belong to a crashed request and may be
# taken over, so a draft can never be stuck in SUBMITTING forever.
SUBMISSION_CLAIM_TIMEOUT = timedelta(minutes=15)

# Errors the session submit view returns *before* it calls the external filing
# API. Only these are safe to release back to DRAFT; any other failure may have
# left a filing submitted, so the draft must not be freed for a blind retry.
_PRE_SUBMIT_ERROR_PREFIXES = (
    "Submission confirmation is required",
    "No case data found",
    "No upload data found",
    "No efile data provided",
    "Missing required fields in efile_data",
    "Court ID is required",
)


def _claim_for_submission(draft: FilingDraft) -> bool:
    """Atomically move a submittable (or stale-claimed) draft into SUBMITTING.

    Only one request can win this transition, so concurrent double-clicks cannot
    each forward to the external API. A claim left behind by a crashed request
    becomes recoverable once it is older than ``SUBMISSION_CLAIM_TIMEOUT``.
    """
    now = timezone.now()
    stale_before = now - SUBMISSION_CLAIM_TIMEOUT
    claimed = (
        FilingDraft.objects.filter(pk=draft.pk)
        .filter(
            Q(status__in=_CLAIMABLE_STATUSES) | Q(status=FilingDraft.Status.SUBMITTING, updated_at__lt=stale_before)
        )
        .update(status=FilingDraft.Status.SUBMITTING, updated_at=now)
    )
    if claimed:
        draft.status = FilingDraft.Status.SUBMITTING
        draft.updated_at = now
    return bool(claimed)


def _release_claim(draft: FilingDraft) -> None:
    """Return a claimed draft to DRAFT when no external submission was attempted."""
    FilingDraft.objects.filter(pk=draft.pk, status=FilingDraft.Status.SUBMITTING).update(
        status=FilingDraft.Status.DRAFT,
        updated_at=timezone.now(),
    )
    draft.status = FilingDraft.Status.DRAFT


def _json_payload(response: JsonResponse) -> dict:
    try:
        return json.loads(response.content.decode(response.charset or "utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return {}


def _failed_before_external_call(payload: dict) -> bool:
    """True only when the submit view rejected the request before calling the API."""
    if "api_status_code" in payload:
        return False
    error = payload.get("error")
    return isinstance(error, str) and error.startswith(_PRE_SUBMIT_ERROR_PREFIXES)


@csrf_exempt
@require_http_methods(["POST"])
def submit_final_filing(request):
    """Submit through the session path, guarding against duplicate external filings."""

    jurisdiction = request.session.get("jurisdiction")
    draft = get_current_draft(request, jurisdiction=jurisdiction, resume_latest=False)

    # Claim the draft before forwarding so a concurrent request can't file twice.
    if draft is not None and not _claim_for_submission(draft):
        return JsonResponse(
            {"success": False, "error": "This filing is already being submitted."},
            status=409,
        )

    response = legacy_submit_final_filing(request)
    payload = _json_payload(response)

    if draft is None:
        return response

    if response.status_code < 400 and payload.get("success") is True:
        draft.mark_submitted(payload.get("api_response") or {})
        clear_current_draft(request)
    elif _failed_before_external_call(payload):
        # No external call happened, so it is safe to free the draft for retry.
        _release_claim(draft)
    else:
        # The API failed, or the outcome is ambiguous (an error after requests.post
        # may mean the filing went through). Record an error and leave it OUT of
        # DRAFT so a blind retry cannot silently double-file. (True exactly-once
        # would require an idempotency key on the external filing API.)
        draft.mark_error({"status_code": response.status_code, "response": payload})

    return response
