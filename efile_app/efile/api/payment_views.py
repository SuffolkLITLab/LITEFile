"""Payment actions that do not require leaving LITEFile."""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from requests import RequestException

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.payment_accounts import ensure_waiver_account
from efile.utils.jurisdiction_stuff import get_jurisdiction_from_request, has_jurisdiction_login


@require_http_methods(["POST"])
def waiver_account(request):
    jurisdiction = get_jurisdiction_from_request(request)
    token = get_tyler_token(request, jurisdiction)
    if not jurisdiction or not has_jurisdiction_login(request, jurisdiction):
        return JsonResponse({"success": False, "error": "Please sign in again."}, status=401)
    preferred_id = ""
    if request.content_type == "application/json":
        try:
            preferred_id = str(json.loads(request.body or "{}").get("preferred_id") or "")
        except (ValueError, AttributeError):
            pass
    try:
        account = ensure_waiver_account(request.user, jurisdiction, token, preferred_id)
    except (RequestException, ValueError):
        return JsonResponse(
            {"success": False, "error": "We could not set up your waiver account. Please try again."}, status=503
        )
    return JsonResponse({"success": True, "data": account})
