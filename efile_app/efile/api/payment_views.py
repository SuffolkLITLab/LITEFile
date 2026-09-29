"""Payment actions that do not require leaving LITEFile."""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from requests import RequestException

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDraft
from efile.services.payment_accounts import ensure_waiver_account, remove_payment_account
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


@require_http_methods(["DELETE"])
def delete_payment_account(request, account_id):
    jurisdiction = get_jurisdiction_from_request(request)
    if not jurisdiction or not has_jurisdiction_login(request, jurisdiction):
        return JsonResponse({"success": False, "error": "Please sign in again."}, status=401)
    try:
        remove_payment_account(jurisdiction, get_tyler_token(request, jurisdiction), account_id)
    except ValueError:
        return JsonResponse({"success": False, "error": "Choose a payment account from your account list."}, status=400)
    except RequestException:
        return JsonResponse(
            {"success": False, "error": "We could not remove this payment method. Please try again."}, status=503
        )
    # Submitted filings keep their payment history. Editable drafts must choose
    # another account and get a fresh quote before they can be submitted.
    FilingDraft.objects.filter(
        user=request.user,
        jurisdiction=jurisdiction,
        status__in=[FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR],
        selected_payment_account_id=account_id,
    ).update(
        selected_payment_account_id="",
        selected_payment_account_name="",
        selected_payment_account_type="",
        quoted_fee_total="",
        quoted_fee_breakdown=[],
        quoted_fee_fingerprint="",
    )
    return JsonResponse({"success": True})
