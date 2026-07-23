import logging

import requests
from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from ..utils.case_data_utils import get_case_data

logger = logging.getLogger(__name__)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class GetCaseDataView(View):
    """API endpoint to return the current draft as the case_data blob."""

    def get(self, request):
        try:
            case_data = get_case_data(request)
            data = {"case_data": case_data}
            for key in ("session_id", "jurisdiction", "existing_case"):
                value = request.session.get(key) or case_data.get(key)
                if value:
                    data[key] = value
            return JsonResponse({"success": True, "data": data})
        except Exception:
            logger.exception("Error retrieving case data")
            return JsonResponse({"success": False, "error": "Server error occurred"}, status=500)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class GetFilingComponentsView(View):
    """API endpoint to get filing components from Suffolk LIT Lab API (proxy to avoid CORS)."""

    def get(self, request):
        try:
            # Get parameters from query string or fallback to session data
            court = request.GET.get("court")
            jurisdiction = request.GET.get("jurisdiction")
            filing_type_id = request.GET.get("filing_type")

            # If not provided in query, try to get from the current draft
            if not court or not filing_type_id:
                case_data = get_case_data(request)
                court = court or case_data.get("court", "cook:cd")
                filing_type_id = filing_type_id or case_data.get("filing_type")

            # If we still don't have filing_type_id, try to get all filing components
            # by using a generic endpoint or a common filing type
            if not filing_type_id:
                # Try to get a list of filing types first to get any filing type ID
                path = f"/jurisdictions/{jurisdiction}/codes/courts/{court}/filing_types"
                filing_types_url = f"{settings.EFSP_URL}{path}"
                filing_types_response = requests.get(filing_types_url, timeout=10)
                if filing_types_response.status_code == 200:
                    filing_types_data = filing_types_response.json()
                    # Use the first available filing type to get components
                    if filing_types_data and len(filing_types_data) > 0:
                        filing_type_id = filing_types_data[0].get("value") or filing_types_data[0].get("code")
                        logger.info(f"Using first available filing type: {filing_type_id}")
                    else:
                        # Fallback to a common filing type ID
                        filing_type_id = "78690"
                        logger.info(f"Using fallback filing type: {filing_type_id}")
                else:
                    filing_type_id = "78690"  # Fallback
                    logger.info(f"Failed to get filing types, using fallback: {filing_type_id}")

            logger.info(f"Getting filing components for court: {court}, filing_type: {filing_type_id}")

            # Build the Suffolk LIT Lab API URL
            path = f"/jurisdictions/{jurisdiction}/codes/courts/{court}/filing_types/{filing_type_id}/filing_components"
            api_url = f"{settings.EFSP_URL}{path}"

            # Make the API request to Suffolk LIT Lab
            response = requests.get(api_url, timeout=10)

            if response.status_code == 200:
                filing_data = response.json()
                return JsonResponse({"success": True, "data": filing_data})
            else:
                logger.error(f"Suffolk API error: {response.status_code} - {response.text}")
                return JsonResponse(
                    {"success": False, "error": f"Failed to fetch filing components: {response.status_code}"},
                    status=response.status_code,
                )

        except requests.RequestException:
            logger.exception("Request error")
            return JsonResponse({"success": False, "error": "Failed to connect to filing components API"}, status=503)
        except Exception:
            logger.exception("Error getting filing components")
            return JsonResponse({"success": False, "error": "Server error occurred"}, status=500)


# Function-based view wrapper for easy URL mapping
get_case_data_api = GetCaseDataView.as_view()
get_filing_components = GetFilingComponentsView.as_view()
