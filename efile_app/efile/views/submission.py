import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from efile.models import FilingDraft
from efile.services.current_drafts import clear_current_draft, get_current_draft
from efile.services.filing_plans import mark_attached_items_filed
from efile.services.submission_errors import PRE_SUBMIT_ERROR_CODES

from .confirmation import LAST_SUBMITTED_DRAFT_SESSION_KEY
from .session_api import submit_final_filing as legacy_submit_final_filing

logger = logging.getLogger(__name__)

# Only a clean DRAFT may be submitted. A draft is deliberately never auto-recovered
# out of SUBMITTING or ERROR: without an idempotency key on the external filing API,
# a retry after an ambiguous outcome could file a second time. Those states require
# manual review instead.
_CLAIMABLE_STATUSES = (FilingDraft.Status.DRAFT,)


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
    return payload.get("error_code") in PRE_SUBMIT_ERROR_CODES


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
        with transaction.atomic():
            draft.mark_submitted(payload.get("api_response") or {})
            mark_attached_items_filed(draft)
        request.session[LAST_SUBMITTED_DRAFT_SESSION_KEY] = draft.pk
        request.session.modified = True
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
