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

from efile.utils.jurisdiction_stuff import get_jurisdiction_from_request

logger = logging.getLogger(__name__)


def get_tyler_token(request, jurisdiction=None):
    """Helper method to retrieve Tyler token from various sources"""
    if jurisdiction is None:
        jurisdiction = get_jurisdiction_from_request(request)

    # Fallback to session
    auth_tokens = request.session.get("auth_tokens", {})
    logger.debug(f"Auth tokens in session: {auth_tokens}")

    # Try different Tyler token key formats
    tyler_token = (
        auth_tokens.get(f"TYLER-TOKEN-{jurisdiction.upper()}")
        or auth_tokens.get(f"tyler_token_{jurisdiction}")
        or auth_tokens.get(f"tyler-token-{jurisdiction}")
    )

    return tyler_token


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
            state = get_jurisdiction_from_request(request)
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
                    case_info["caseCategoryCode"] = case_value["caseCategoryText"]["value"]
                    api_url = f"{settings.EFSP_URL}/jurisdictions/{state}/codes/courts/{court}/categories/{case_info['caseCategoryCode']}"
                    category_resp = requests.get(api_url, headers=headers, timeout=30)
                    if category_resp.ok:
                        data = category_resp.json()
                        case_info["caseCategoryName"] = data["name"]

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
                                    case_info["caseTypeCode"] = item["value"]["caseTypeText"]["value"]
                                    api_url = f"{settings.EFSP_URL}/jurisdictions/{state}/codes/courts/{court}/case_types/{case_info['caseTypeCode']}"
                                    case_resp = requests.get(api_url, headers=headers, timeout=30)
                                    if case_resp.ok:
                                        data = category_resp.json()
                                        case_info["caseTypeName"] = data["name"]
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

        success = True
        if not case_info.get("caseTrackingID") and not case_info.get("caseCategoryText"):
            logger.warning(f"Could not extract case information from API response for case {case_number}: {api_data}")
            # Return what we have from the API for debugging
            case_info = api_data[0] if api_data and len(api_data) > 0 else {}
            success = False

        response = JsonResponse(
            {
                "success": success,
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
