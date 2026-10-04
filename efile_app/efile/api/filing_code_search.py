"""Read-only search and live validation; applying a result edits the form only."""

import json
import logging
from datetime import timedelta

import requests
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from efile.services.filing_code_search import current_index, rules, search_grouped_paths, search_paths, validate_path
from efile.utils.jurisdiction_stuff import has_jurisdiction_login

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def filing_code_search(request):
    jurisdiction = request.GET.get("jurisdiction", "").lower()
    if jurisdiction not in rules()[0]["jurisdictions"]:
        return JsonResponse({"error": "Choose a supported jurisdiction."}, status=400)
    if not has_jurisdiction_login(request, jurisdiction):
        return JsonResponse({"error": "Sign in to this jurisdiction to search filing codes."}, status=403)
    initial = request.GET.get("existing_case", "no") != "yes"
    index = current_index(jurisdiction)
    if index is None:
        return JsonResponse({"error": "Code search is not available yet. Use the court lists to continue."}, status=503)
    if request.GET.get("path_id"):
        try:
            path_id = int(request.GET["path_id"])
        except ValueError:
            return JsonResponse({"error": "Invalid filing path."}, status=400)
        path = index.paths.filter(pk=path_id, initial=initial).select_related("index").first()
        if path is None:
            return JsonResponse({"error": "The code list has changed. Search again."}, status=409)
        try:
            return JsonResponse({"path": validate_path(path)})
        except ValueError as error:
            return JsonResponse({"error": str(error)}, status=409)
        except requests.RequestException:
            logger.warning("Could not revalidate filing search path %s", path.pk)
            return JsonResponse({"error": "The court lists could not be checked. Try again."}, status=503)
    query = request.GET.get("q", "").strip()
    purpose = request.GET.get("purpose", "")
    document = request.GET.get("document", "")
    if purpose not in ("", "starting", "responding", "either", "unknown") or document not in (
        "",
        "main",
        "attachment",
        "unknown",
    ):
        return JsonResponse({"error": "Choose a valid search filter."}, status=400)
    role = request.GET.get("role", "")
    property_kind = request.GET.get("property", "")
    relief = request.GET.get("relief", "")
    if (
        role not in ("", "tenant", "landlord")
        or property_kind not in ("", "residential", "commercial")
        or relief not in ("", "possession", "money")
    ):
        return JsonResponse({"error": "Choose a valid case-type filter."}, status=400)
    try:
        case_filters = json.loads(request.GET.get("case_filters", "{}"))
        if not isinstance(case_filters, dict):
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({"error": "Choose valid case-type filters."}, status=400)
    try:
        offset = int(request.GET.get("offset", "0"))
    except ValueError:
        offset = -1
    if not 0 <= offset <= 10000 or not 1 <= len(query) <= 160:
        return JsonResponse(
            {"error": "Enter a search of up to 160 characters and use a valid results page."}, status=400
        )
    try:
        if request.GET.get("grouped") == "true":
            result = search_grouped_paths(
                index,
                query,
                initial=initial,
                offset=offset,
                group_key=request.GET.get("group", ""),
                court=request.GET.get("court", ""),
                purpose=purpose,
                document=document,
                context=request.GET.get("context", ""),
                postal_code=request.GET.get("zip", "").strip(),
                role=role,
                property_kind=property_kind,
                relief=relief,
                case_topic=request.GET.get("case_topic", ""),
                case_filters=case_filters,
            )
        else:
            if purpose or document:
                return JsonResponse({"error": "Use grouped search with filing-type filters."}, status=400)
            result = search_paths(index, query, initial=initial, offset=offset)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=409)
    result.update(
        {
            "refreshed_at": index.refreshed_at.isoformat(),
            "stale": index.refreshed_at < timezone.now() - timedelta(days=2),
        }
    )
    response = JsonResponse(result)
    response["Cache-Control"] = "no-store"
    return response
