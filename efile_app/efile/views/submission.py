import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from efile.services.current_drafts import clear_current_draft, get_current_draft

from .session_api import submit_final_filing as legacy_submit_final_filing

logger = logging.getLogger(__name__)


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
    """Submit through the legacy session path and mirror the result to the durable draft."""

    jurisdiction = request.session.get("jurisdiction")
    draft = get_current_draft(request, jurisdiction=jurisdiction, resume_latest=False)

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

    return response
