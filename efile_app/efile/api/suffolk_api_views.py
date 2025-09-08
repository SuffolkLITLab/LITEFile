"""
API views for Suffolk LIT Lab integration
"""

import json
import logging

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


def get_state_from_request(request):
    """Extract state from request URL or parameters"""
    # Try to get state from query parameters first
    state = request.GET.get("state")
    if state:
        return state.lower()

    # Try to extract from URL path (e.g., /jurisdictions/illinois/)
    path = request.path
    if "/jurisdictions/" in path:
        path_parts = path.split("/jurisdictions/")
        if len(path_parts) > 1:
            state_part = path_parts[1].split("/")[0]
            if state_part:
                return state_part.lower()

    # Default to Illinois if no state found
    return "illinois"


def get_tyler_token(request, state=None):
    """Helper method to retrieve Tyler token from various sources"""
    if state is None:
        state = get_state_from_request(request)

    auth_tokens = request.session.get("auth_tokens", {})
    logger.debug(f"Auth tokens in session: {auth_tokens}")

    # Try different Tyler token key formats
    tyler_token = (
        auth_tokens.get(f"TYLER-TOKEN-{state.upper()}")
        or auth_tokens.get(f"tyler_token_{state}")
        or auth_tokens.get(f"tyler-token-{state}")
    )

    if tyler_token:
        return tyler_token

    return None


@csrf_exempt
@require_http_methods(["GET", "POST", "OPTIONS"])
def lookup_case(request):
    """
    Look up a case using Suffolk LIT Lab API

    For GET requests, expects query parameters: court and caseNumber
    For POST requests, expects JSON body with: court and caseNumber

    Returns case information including caseTrackingID and caseCategoryText
    """

    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        response = JsonResponse({})
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
        return response

    try:
        # Get parameters based on request method
        if request.method == "GET":
            court = request.GET.get("court")
            case_number = request.GET.get("caseNumber")
            jurisdiction = request.GET.get("jurisdiction")
        else:  # POST
            data = json.loads(request.body)
            court = data.get("court")
            case_number = data.get("caseNumber")
            jurisdiction = data.get("jurisdiction")

        if not court or not case_number:
            response = JsonResponse({"success": False, "error": "Both court and caseNumber are required"}, status=400)
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
            return response

        # Suffolk eFile API endpoint - build URL with court and case number
        # Use provided jurisdiction or fall back to request-based detection
        if jurisdiction:
            state = jurisdiction.lower()
        else:
            state = get_state_from_request(request)
        api_url = f"{settings.EFSP_URL}/jurisdictions/{state}/cases/courts/{court}/cases"

        # Add query parameter for docket number
        params = {"docket_number": case_number}

        logger.info(f"Looking up case {case_number} in court {court} at {api_url}")

        # Get authentication credentials dynamically
        tyler_token = get_tyler_token(request, state)
        api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)

        headers = {
            "Accept": "application/json",
            "User-Agent": f"{state.title()}-eFile-Client/1.0",
            "X-API-Key": api_key if api_key else "",
        }

        # Add Tyler token if available
        if tyler_token:
            headers[f"tyler-token-{state}"] = tyler_token
        else:
            # Log that no token was found for debugging
            logger.info(
                "No Tyler token found for state '%s' in Suffolk case lookup request",
                state,
            )

        # Make the API request - using GET with query parameters
        response = requests.get(api_url, params=params, headers=headers, timeout=30)

        response.raise_for_status()
        api_data = response.json()

        # Extract relevant information from the eFile API response
        # The response should be an array of case objects
        case_info = {}

        if api_data and len(api_data) > 0:
            # Take the first case from the response
            case_data = api_data[0]

            # Extract case information from the eFile API response structure
            if "value" in case_data:
                case_value = case_data["value"]

                # Extract caseTrackingID
                if "caseTrackingID" in case_value and "value" in case_value["caseTrackingID"]:
                    case_info["caseTrackingID"] = case_value["caseTrackingID"]["value"]

                # Extract case category
                if "caseCategoryText" in case_value and "value" in case_value["caseCategoryText"]:
                    case_info["caseCategoryText"] = case_value["caseCategoryText"]["value"]

                # Extract case title
                if "caseTitleText" in case_value and "value" in case_value["caseTitleText"]:
                    case_info["caseTitle"] = case_value["caseTitleText"]["value"]

                # Extract case docket ID
                if "caseDocketID" in case_value and "value" in case_value["caseDocketID"]:
                    case_info["caseDocketID"] = case_value["caseDocketID"]["value"]
                else:
                    case_info["caseDocketID"] = case_number

                # Extract case type from extensions if available
                if "rest" in case_value:
                    for item in case_value["rest"]:
                        if item.get("name") == "{urn:tyler:ecf:extensions:Common}CaseAugmentation":
                            if "value" in item and "caseTypeText" in item["value"]:
                                if "value" in item["value"]["caseTypeText"]:
                                    case_info["caseTypeText"] = item["value"]["caseTypeText"]["value"]
                                break
            else:
                # If no 'value' key, try to extract directly
                case_info = {
                    "caseTrackingID": case_data.get("caseTrackingID", ""),
                    "caseCategoryText": case_data.get("caseCategoryText", ""),
                    "caseTitle": case_data.get("caseTitleText", ""),
                    "caseDocketID": case_data.get("caseDocketID", case_number),
                    "caseTypeText": case_data.get("caseTypeText", ""),
                }

        if not case_info.get("caseTrackingID") and not case_info.get("caseCategoryText"):
            logger.warning(f"Could not extract case information from API response for case {case_number}")
            # Return what we have from the API for debugging
            case_info = api_data[0] if api_data and len(api_data) > 0 else {}

        response = JsonResponse(
            {
                "success": True,
                "caseInfo": case_info,
                "fullResponse": api_data,  # Include full response for debugging
            }
        )
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
        return response

    except json.JSONDecodeError:
        # This only applies to POST requests
        response = JsonResponse({"success": False, "error": "Invalid JSON in request body"}, status=400)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
        return response

    except RequestException as e:
        logger.error(f"Suffolk API request failed: {str(e)}")
        response = JsonResponse(
            {"success": False, "error": "Failed to connect to Suffolk API", "details": str(e)}, status=500
        )
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
        return response

    except Exception as e:
        logger.error(f"Unexpected error in case lookup: {str(e)}")
        response = JsonResponse(
            {"success": False, "error": "An unexpected error occurred", "details": str(e)}, status=500
        )
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
        return response
