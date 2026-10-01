"""Read-only availability checks as a filer changes court and type selections."""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from efile.services.filing_availability import filing_unavailable_message
from efile.utils.config_loader import InvalidJurisdiction


@require_http_methods(["GET"])
def get_filing_availability(request):
    try:
        message = filing_unavailable_message(
            request.GET.get("jurisdiction") or request.session.get("jurisdiction"),
            request.GET.get("court", ""),
            case_category=request.GET.get("case_category_name", ""),
            case_type=request.GET.get("case_type_name", ""),
            filing_types=request.GET.getlist("filing_type_name"),
        )
    except InvalidJurisdiction as error:
        return JsonResponse({"success": False, "error": str(error)}, status=400)
    response = JsonResponse({"success": True, "available": not bool(message), "message": message})
    response.headers["Cache-Control"] = "no-store"
    return response
