import json
import logging

import requests
from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

logger = logging.getLogger(__name__)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class GetCaseDataView(View):
    """API endpoint to retrieve case data from session."""

    def get(self, request):
        try:
            # Get case data from session
            case_data = request.session.get("case_data", {})

            logger.debug(f"Retrieved case data from session: {case_data}")

            return JsonResponse({"success": True, "data": case_data})

        except Exception:
            logger.exception("Error retrieving case data: {e}")
            return JsonResponse({"success": False, "error": "Server error occurred"}, status=500)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SaveCaseDataView(View):
    """API endpoint to save case data to session."""

    def post(self, request):
        try:
            data = json.loads(request.body)

            # Extract case data from form submission
            case_data = {
                "court": data.get("court", ""),
                "case_category": data.get("case_category", ""),
                "case_type": data.get("case_type", ""),
                "filing_type": data.get("filing_type", ""),
                "document_type": data.get("document_type", ""),
                "petitioner_first_name": data.get("petitioner_first_name", ""),
                "petitioner_last_name": data.get("petitioner_last_name", ""),
                "petitioner_address": data.get("petitioner_address", ""),
                "petitioner_party_type": data.get("petitioner_party_type", ""),  # Add party type
                "new_first_name": data.get("new_first_name", ""),
                "new_last_name": data.get("new_last_name", ""),
                "new_name_party_type": data.get("new_name_party_type", ""),  # Add party type
                "optional_services": data.get("optional_services", []),
            }

            # Validate required fields
            required_fields = ["court", "case_category", "case_type", "filing_type", "document_type"]
            missing_fields = [field for field in required_fields if not case_data.get(field)]

            if missing_fields:
                err_missing = f"Missing required fields: {', '.join(missing_fields)}"
                return JsonResponse({"success": False, "error": err_missing}, status=400)

            # For name change cases, validate party information
            if "name change" in case_data.get("case_type", "").lower():
                party_fields = ["petitioner_first_name", "petitioner_last_name", "new_first_name", "new_last_name"]
                missing_party_fields = [field for field in party_fields if not case_data.get(field)]

                if missing_party_fields:
                    err_party = f"Missing party information for name change case: {', '.join(missing_party_fields)}"
                    return JsonResponse({"success": False, "error": err_party}, status=400)

            # Save to session
            request.session["case_data"] = case_data
            request.session.modified = True

            logger.debug(f"Saved case data to session: {case_data}")

            return JsonResponse({"success": True, "message": "Case data saved successfully"})

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
        except Exception:
            logger.exception("Error saving case data: {e}")
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

            # If not provided in query, try to get from session
            if not court or not filing_type_id:
                case_data = request.session.get("case_data", {})
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
                        print(f"Using first available filing type: {filing_type_id}")
                    else:
                        # Fallback to a common filing type ID
                        filing_type_id = "78690"
                        print(f"Using fallback filing type: {filing_type_id}")
                else:
                    filing_type_id = "78690"  # Fallback
                    print(f"Failed to get filing types, using fallback: {filing_type_id}")

            print(f"Getting filing components for court: {court}, filing_type: {filing_type_id}")

            # Build the Suffolk LIT Lab API URL
            path = f"/jurisdictions/{jurisdiction}/codes/courts/{court}/filing_types/{filing_type_id}/filing_components"
            api_url = f"{settings.EFSP_URL}{path}"

            # Make the API request to Suffolk LIT Lab
            response = requests.get(api_url, timeout=10)

            if response.status_code == 200:
                filing_data = response.json()
                return JsonResponse({"success": True, "data": filing_data})
            else:
                print(f"Suffolk API error: {response.status_code} - {response.text}")
                return JsonResponse(
                    {"success": False, "error": f"Failed to fetch filing components: {response.status_code}"},
                    status=response.status_code,
                )

        except requests.RequestException as e:
            print(f"Request error: {e}")
            return JsonResponse({"success": False, "error": "Failed to connect to filing components API"}, status=503)
        except Exception as e:
            print(f"Error getting filing components: {e}")
            return JsonResponse({"success": False, "error": "Server error occurred"}, status=500)


# Function-based view wrapper for easy URL mapping
get_case_data = GetCaseDataView.as_view()
save_case_data = SaveCaseDataView.as_view()
get_filing_components = GetFilingComponentsView.as_view()
