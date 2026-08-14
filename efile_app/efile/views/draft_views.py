import json
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import create_current_draft, get_current_draft
from efile.services.drafts import draft_snapshot
from efile.utils.django_helpers import flush_cache_stay_logged_in
from efile.workflow import WorkflowStepKey, get_step_url

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def create_draft_view(request, jurisdiction):
    """Start a durable draft for the current user/session."""

    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
    if not get_tyler_token(request, jurisdiction):
        return JsonResponse({"success": False, "error": "Jurisdiction authorization required"}, status=403)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"success": False, "error": "JSON body must be an object"}, status=400)

    flush_cache_stay_logged_in(request.session)
    draft = create_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.FILING_PATH,
        workflow_version=2,
    )
    logger.info("Created durable draft id=%s jurisdiction=%s", draft.pk, jurisdiction)

    return JsonResponse(
        {
            "success": True,
            "data": {"filing_draft": draft_snapshot(draft)},
            "redirect_url": get_step_url(WorkflowStepKey.FILING_PATH, jurisdiction),
        }
    )


@require_http_methods(["GET"])
def get_current_draft_view(request):
    """Return the durable draft attached to this session/user."""

    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)

    draft = get_current_draft(request)
    return JsonResponse({"success": True, "data": {"filing_draft": draft_snapshot(draft)}})
