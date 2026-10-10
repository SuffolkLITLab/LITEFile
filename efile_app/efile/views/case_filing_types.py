from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.case_filing_types import permitted_filing_types
from efile.services.current_drafts import get_current_draft
from efile.services.filing_type_proposals import resolve_proposal


@require_http_methods(["GET"])
def case_filing_types(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return JsonResponse({"success": False}, status=401)
    draft = get_current_draft(request, jurisdiction=jurisdiction, resume_latest=False)
    if draft is None:
        return JsonResponse({"success": False, "error": "Choose a filing draft."}, status=404)
    try:
        choices = permitted_filing_types(draft)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=409)
    return JsonResponse({"success": True, "data": choices, "suggestion": resolve_proposal(draft, choices)})
