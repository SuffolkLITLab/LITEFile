"""
API views for filing operations and document management
"""

import json
import logging

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..utils.case_data_utils import get_case_data
from ..utils.proxy_connection import get_party_type_code_from_api
from .base import APIResponseMixin

logger = logging.getLogger(__name__)

# TODO(brycew): this file doesn't work in it's current state. Keeping
# around for later refactors, when we inevitably want to start letting users
# handle filings themselves / see current status, etc.


class FilingAPIViews(APIResponseMixin):
    """API views for filing operations"""

    @staticmethod
    @require_http_methods(["GET"])
    def get_filings(request):
        """Get user's filings"""
        try:
            # API call to get user's filings
            api_url = "https://suffolkefile.com/api/filings"
            response = requests.get(api_url, timeout=30)
            logger.debug(
                "Get filings response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )

            if response.status_code == 200:
                data = response.json()
                return FilingAPIViews.success_response(data.get("filings", []))
            else:
                return FilingAPIViews.error_response("Failed to fetch filings")

        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def create_filing(request):
        """Create a new filing"""
        try:
            data = json.loads(request.body)

            # Validate required fields
            required_fields = ["case_category", "case_type", "filing_type", "county"]
            missing_fields = [field for field in required_fields if not data.get(field)]

            if missing_fields:
                return FilingAPIViews.error_response(f"Missing required fields: {', '.join(missing_fields)}")

            # API call to create filing
            api_url = "https://suffolkefile.com/api/filings"
            logger.debug("POST %s payload keys=%s", api_url, list(data.keys()))
            response = requests.post(api_url, json=data, timeout=30)
            logger.debug(
                "Create filing response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )

            if response.status_code == 201:
                filing_data = response.json()
                return FilingAPIViews.success_response(filing_data, "Filing created successfully")
            else:
                return FilingAPIViews.error_response("Failed to create filing")

        except json.JSONDecodeError:
            return FilingAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def get_filing_detail(request, filing_id):
        """Get details for a specific filing"""
        try:
            # API call to get filing details
            api_url = f"https://suffolkefile.com/api/filings/{filing_id}"
            response = requests.get(api_url, timeout=30)
            logger.debug(
                "Filing detail response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )

            if response.status_code == 200:
                filing_data = response.json()
                return FilingAPIViews.success_response(filing_data)
            elif response.status_code == 404:
                return FilingAPIViews.error_response("Filing not found", 404)
            else:
                return FilingAPIViews.error_response("Failed to fetch filing details")

        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["PUT"])
    @csrf_exempt
    def update_filing(request, filing_id):
        """Update an existing filing"""
        try:
            data = json.loads(request.body)

            # API call to update filing
            api_url = f"https://suffolkefile.com/api/filings/{filing_id}"
            logger.debug("PUT %s payload keys=%s", api_url, list(data.keys()))
            response = requests.put(api_url, json=data, timeout=30)
            logger.debug(
                "Update filing response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )

            if response.status_code == 200:
                filing_data = response.json()
                return FilingAPIViews.success_response(filing_data, "Filing updated successfully")
            elif response.status_code == 404:
                return FilingAPIViews.error_response("Filing not found", 404)
            else:
                return FilingAPIViews.error_response("Failed to update filing")

        except json.JSONDecodeError:
            return FilingAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["DELETE"])
    @csrf_exempt
    def delete_filing(request, filing_id):
        """Delete a filing"""
        try:
            # API call to delete filing
            api_url = f"https://suffolkefile.com/api/filings/{filing_id}"
            logger.debug("DELETE %s", api_url)
            response = requests.delete(api_url, timeout=30)
            logger.debug(
                "Delete filing response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )

            if response.status_code == 204:
                return FilingAPIViews.success_response({}, "Filing deleted successfully")
            elif response.status_code == 404:
                return FilingAPIViews.error_response("Filing not found", 404)
            else:
                return FilingAPIViews.error_response("Failed to delete filing")

        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")


@csrf_exempt
@require_http_methods(["POST"])
def _unused_create_filing(request):
    """Create a filing with Suffolk LIT Lab API using collected case data."""

    try:
        # Get case data from session
        case_data = get_case_data(request)

        if not case_data:
            return JsonResponse(
                {"success": False, "error": "No case data found. Please complete the expert form first."}, status=400
            )

        # Get auth tokens
        auth_tokens = request.session.get("auth_tokens")
        if not auth_tokens or "token" not in auth_tokens:
            return JsonResponse(
                {"success": False, "error": "Authentication required. Please log in first."}, status=401
            )

        # Transform case data to Suffolk API payload format
        filing_payload = transform_case_data_to_filing_payload(case_data, request)

        # Make POST request to Suffolk LIT Lab filing API
        path = "/filings/"
        api_url = f"{settings.EFSP_URL}{path}"

        headers = {"Authorization": f"Bearer {auth_tokens['token']}", "Content-Type": "application/json"}

        # Safe pre-request logging
        logger.debug(
            "POST %s with headers keys=%s payload keys=%s",
            api_url,
            list(headers.keys()),
            list(filing_payload.keys()),
        )
        response = requests.post(api_url, headers=headers, json=filing_payload, timeout=30)
        logger.debug(
            "Create filing response: status=%s content_type=%s",
            response.status_code,
            response.headers.get("Content-Type"),
        )

        if response.status_code == 201:
            # Filing created successfully
            filing_data = response.json()

            # Save filing ID to session for future reference
            request.session["current_filing_id"] = filing_data.get("id")
            request.session.modified = True

            return JsonResponse(
                {
                    "success": True,
                    "filing_id": filing_data.get("id"),
                    "message": "Filing created successfully",
                    "data": filing_data,
                }
            )
        else:
            # API error
            error_detail = response.text
            try:
                error_json = response.json()
                error_detail = error_json.get("detail", error_json)
            except ValueError:
                pass

            return JsonResponse(
                {
                    "success": False,
                    "error": f"Filing creation failed: {error_detail}",
                    "status_code": response.status_code,
                },
                status=response.status_code,
            )

    except requests.RequestException as e:
        return JsonResponse({"success": False, "error": f"Network error: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Unexpected error: {str(e)}"}, status=500)


def transform_case_data_to_filing_payload(case_data, request=None):
    """
    Transform collected case data into Suffolk LIT Lab API filing payload format.
    """

    # Base filing payload structure
    payload = {
        "jurisdiction": case_data.get("jurisdiction"),
        "court": case_data.get("court"),
        "category": case_data.get("case_category"),
        "case_type": case_data.get("case_type"),
        "filing_type": case_data.get("filing_type"),
        "document_type": case_data.get("document_type"),
        "parties": [],
        "optional_services": case_data.get("optional_services", []),
    }

    # Add petitioner party if this is a name change case
    if "name change" in case_data.get("case_type", "").lower():
        # Add petitioner
        if case_data.get("petitioner_first_name") or case_data.get("petitioner_last_name"):
            # Use party type from session data, or determine it from API
            party_type = case_data.get("petitioner_party_type")
            if not party_type:
                party_type = determine_party_type_for_new_case(case_data)

            petitioner = {
                "party_type": party_type,
                "name": {
                    "first": case_data.get("petitioner_first_name", ""),
                    "last": case_data.get("petitioner_last_name", ""),
                    "full": (
                        f"{case_data.get('petitioner_first_name', '')} {case_data.get('petitioner_last_name', '')}"
                    ).strip(),
                },
                "address": case_data.get("petitioner_address", ""),
                "role": "Petitioner",  # Keep role as readable text
            }
            payload["parties"].append(petitioner)
    else:
        # For non-name change cases, still add the party information if available
        if case_data.get("first_name") or case_data.get("last_name"):
            # Determine party type based on existing case status
            existing_case = None
            if request:
                existing_case = request.session.get("existing_case")

            # Also check if existing_case is stored in case_data
            if not existing_case:
                existing_case = case_data.get("existing_case")

            if existing_case == "yes":
                # When responding to existing case, use intelligent party type determination
                party_type = case_data.get("party_type") or determine_party_type_for_existing_case(case_data)
            else:
                # For new cases, use intelligent party type determination
                party_type = case_data.get("party_type") or determine_party_type_for_new_case(case_data)

            # Determine role name for display (keep as readable text)
            if existing_case == "yes":
                role_name = "Defendant" if "DEF" in party_type else "Respondent" if "RES" in party_type else "Party"
            else:
                role_name = "Petitioner" if "PET" in party_type else "Plaintiff" if "PLA" in party_type else "Party"

            party = {
                "party_type": party_type,
                "name": {
                    "first": case_data.get("first_name", ""),
                    "last": case_data.get("last_name", ""),
                    "full": (f"{case_data.get('first_name', '')} {case_data.get('last_name', '')}").strip(),
                },
                "address": case_data.get("address", ""),
                "role": role_name,
            }
            payload["parties"].append(party)

        # Add name sought information as additional case details
        if case_data.get("new_first_name") or case_data.get("new_last_name"):
            payload["name_change_details"] = {
                "new_name": {
                    "first": case_data.get("new_first_name", ""),
                    "last": case_data.get("new_last_name", ""),
                    "full": (f"{case_data.get('new_first_name', '')} {case_data.get('new_last_name', '')}").strip(),
                }
            }

    # Add case metadata
    payload["metadata"] = {
        "created_via": "illinois_efile_system",
        "case_classification": {
            "court": case_data.get("court"),
            "category": case_data.get("case_category"),
            "case_type": case_data.get("case_type"),
            "filing_type": case_data.get("filing_type"),
            "document_type": case_data.get("document_type"),
        },
    }

    return payload


def determine_party_type_for_new_case(case_data):
    """
    Determine the appropriate party type for a new case.
    This fetches actual party type codes from the API.
    """
    court_code = case_data.get("court")
    case_type_code = case_data.get("case_type")
    case_type = case_data.get("case_type", "").lower()
    jurisdiction = case_data.get("jurisdiction")

    if not court_code or not case_type_code:
        logger.warning("Missing court or case_type for party type determination")
        return "PET"  # Default fallback code for petitioner

    # Determine target party type name based on case type
    target_party_name = None

    if "name change" in case_type:
        target_party_name = "petitioner"
    elif "civil" in case_type:
        target_party_name = "plaintiff"
    elif "family" in case_type:
        target_party_name = "petitioner"
    elif "probate" in case_type:
        target_party_name = "petitioner"
    else:
        target_party_name = "petitioner"

    # Get the actual party type code from API
    party_code = get_party_type_code_from_api(
        court_code, case_type_code, jurisdiction, target_party_name=target_party_name
    )

    # Fallback codes if API call fails
    if not party_code:
        if target_party_name == "plaintiff":
            return "PLA"
        elif target_party_name == "petitioner":
            return "PET"
        else:
            return "PET"

    return party_code


def determine_party_type_for_existing_case(case_data):
    """
    Determine the appropriate party type when responding to an existing case.
    This fetches actual party type codes from the API.
    """
    court_code = case_data.get("court")
    case_type_code = case_data.get("case_type")
    case_type = case_data.get("case_type", "").lower()
    filing_type = case_data.get("filing_type", "").lower()
    jurisdiction = case_data.get("jurisdiction")

    if not court_code or not case_type_code:
        logger.warning("Missing court or case_type for party type determination")
        return "DEF"  # Default fallback code

    # Determine target party type name based on case and filing type
    target_party_name = None

    if "criminal" in case_type:
        target_party_name = "defendant"
    elif "civil" in case_type or "family" in case_type:
        if "answer" in filing_type or "response" in filing_type:
            target_party_name = "respondent"
        else:
            target_party_name = "defendant"
    elif "probate" in case_type:
        target_party_name = "interested party"
    else:
        target_party_name = "defendant"

    # Get the actual party type code from API
    party_code = get_party_type_code_from_api(
        court_code, case_type_code, jurisdiction, target_party_name=target_party_name
    )

    # Fallback codes if API call fails
    if not party_code:
        if target_party_name == "defendant":
            return "DEF"
        elif target_party_name == "respondent":
            return "RES"
        elif target_party_name == "interested party":
            return "INT"
        else:
            return "DEF"

    return party_code


# Individual view functions for URL mapping
get_filings = FilingAPIViews.get_filings
create_filing = FilingAPIViews.create_filing
get_filing_detail = FilingAPIViews.get_filing_detail
update_filing = FilingAPIViews.update_filing
delete_filing = FilingAPIViews.delete_filing
