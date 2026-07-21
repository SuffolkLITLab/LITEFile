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

_CLAIMABLE_STATUSES = (FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR)


def _claim_for_submission(draft: FilingDraft) -> bool:
    """Atomically move a submittable draft into SUBMITTING.

    Only one request can win this transition, so concurrent double-clicks or
    retries cannot each forward to the external filing API and create duplicates.
    """
    claimed = FilingDraft.objects.filter(pk=draft.pk, status__in=_CLAIMABLE_STATUSES).update(
        status=FilingDraft.Status.SUBMITTING,
        updated_at=timezone.now(),
    )
    if claimed:
        draft.status = FilingDraft.Status.SUBMITTING
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


def _submission_attempt_failed(response: JsonResponse, payload: dict) -> bool:
    if "api_status_code" in payload:
        return True

    error = payload.get("error")
    if not isinstance(error, str):
        return False

    return error.startswith("Filing submission failed:") or error.startswith("Network error during filing submission:")


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
    elif _submission_attempt_failed(response, payload):
        draft.mark_error(
            {
                "status_code": response.status_code,
                "response": payload,
            }
        )
    else:
        # A precondition failed before any external call (e.g. missing data);
        # release the claim so the user can fix it and retry.
        _release_claim(draft)

    return response
