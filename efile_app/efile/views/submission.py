import json
import logging

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from efile.models import FilingDraft
from efile.services.current_drafts import clear_current_draft, get_current_draft

from .session_api import submit_final_filing as legacy_submit_final_filing

logger = logging.getLogger(__name__)

# Only a clean DRAFT may be submitted. A draft is deliberately never auto-recovered
# out of SUBMITTING or ERROR: without an idempotency key on the external filing API,
# a retry after an ambiguous outcome could file a second time. Those states require
# manual review instead.
_CLAIMABLE_STATUSES = (FilingDraft.Status.DRAFT,)

# Errors the session submit view returns *before* it calls the external filing
# API. Only these -- and a confirmed API rejection -- are safe to release back to
# DRAFT; any other failure may have left a filing submitted.
#
# Matching on message text is why new pre-call rejections should set
# `"pre_submit": True` on their response instead of being added here: a reworded
# message would otherwise silently start parking drafts in ERROR, locking the
# filer out of a retry for something that never reached the court.
_PRE_SUBMIT_ERROR_PREFIXES = (
    "Submission confirmation is required",
    "No case data found",
    "No upload data found",
    "No efile data provided",
    "Missing required fields in efile_data",
    "Court ID is required",
)


def _claim_for_submission(draft: FilingDraft) -> bool:
    """Atomically move a DRAFT into SUBMITTING.

    Only one request can win this transition, so concurrent double-clicks cannot
    each forward to the external API. A draft already SUBMITTING or ERROR is not
    reclaimed here -- those are not safe to retry automatically.
    """
    claimed = FilingDraft.objects.filter(pk=draft.pk, status__in=_CLAIMABLE_STATUSES).update(
        status=FilingDraft.Status.SUBMITTING,
        updated_at=timezone.now(),
    )
    if claimed:
        draft.status = FilingDraft.Status.SUBMITTING
    return bool(claimed)


def _release_claim(draft: FilingDraft) -> None:
    """Return a claimed draft to DRAFT when nothing was filed (pre-call or rejection)."""
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
    if payload.get("pre_submit") is True:
        return True
    error = payload.get("error")
    return isinstance(error, str) and error.startswith(_PRE_SUBMIT_ERROR_PREFIXES)


def _confirmed_api_rejection(payload: dict) -> bool:
    """True when the filing API answered with a 4xx: the filing was definitely not accepted."""
    code = payload.get("api_status_code")
    # A timeout is ambiguous, and a conflict can mean the filing already exists.
    return isinstance(code, int) and 400 <= code < 500 and code not in (408, 409)


@csrf_exempt
@require_http_methods(["POST"])
def submit_final_filing(request):
    """Submit through the session path, guarding against duplicate external filings."""

    jurisdiction = request.session.get("jurisdiction")
    draft = get_current_draft(request, jurisdiction=jurisdiction, resume_latest=False)

    # Claim the draft before forwarding so a concurrent request can't file twice.
    if draft is not None and not _claim_for_submission(draft):
        return JsonResponse(
            {"success": False, "error": "This filing can't be submitted again automatically."},
            status=409,
        )

    response = legacy_submit_final_filing(request)
    payload = _json_payload(response)

    if draft is None:
        return response

    if response.status_code < 400 and payload.get("success") is True:
        draft.mark_submitted(payload.get("api_response") or {})
        clear_current_draft(request)
    elif _failed_before_external_call(payload) or _confirmed_api_rejection(payload):
        # Nothing was filed (rejected before the call, or the API refused it),
        # so it is safe to return the draft to DRAFT for a corrected retry.
        _release_claim(draft)
    else:
        # Ambiguous: a network error or an error after requests.post may mean the
        # filing went through. Leave it ERROR for manual review -- ERROR is not
        # claimable, so a click cannot silently re-file.
        draft.mark_error({"status_code": response.status_code, "response": payload})

    return response
