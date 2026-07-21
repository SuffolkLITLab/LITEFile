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

from efile.utils.jurisdiction_stuff import get_jurisdiction_from_request

from ..utils.case_data_utils import get_case_data
from ..utils.proxy_connection import get_headers
from .base import APIResponseMixin

logger = logging.getLogger(__name__)

# TODO(brycew): this file doesn't work in it's current state. Keeping
# around for later refactors, when we inevitably want to start letting users
# handle filings themselves / see current status, etc.


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


class FilingAPIViews(APIResponseMixin):
    """API views for filing operations"""

    @staticmethod
    @require_http_methods(["GET"])
    def get_filings(request):
        try:
            # Get all filings in all courts between now and a specified time
            jurisdiction = get_jurisdiction_from_request(request)
            start_date = request.GET.get("start_date")

            if not jurisdiction:
                return JsonResponse({"success": False, "error": "Jurisdiction parameter is required"}, status=400)

            court = "0"  # hardcoded to get filings from all courts
            before_date = None  # defaults to now

            api_url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/filingreview/courts/{court}/filings"

            # Add query parameter for docket number
            params = {
                "start_date": start_date if start_date else None,
                "before_date": before_date if before_date else None,
            }

            logger.info(f"Looking up filings in all courts at {api_url}")

            # Get authentication credentials dynamically
            tyler_token = get_tyler_token(request, jurisdiction)

            headers = get_headers()
            # Add Tyler token if available
            if tyler_token:
                headers[f"tyler-token-{jurisdiction}"] = tyler_token
            else:
                # Log that no token was found for debugging
                logger.info(
                    "No Tyler token found for state '%s' in Suffolk case lookup request",
                    jurisdiction,
                )

            # Make the API request - using GET with query parameters
            response = requests.get(api_url, params=params, headers=headers, timeout=30)
            logger.debug(
                "Get filings response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )
            response.raise_for_status()
            api_data = [FilingAPIViews.convert_filing_data(filing) for filing in response.json()]
            return FilingAPIViews.success_response(api_data)
        except requests.RequestException as e:
            logger.exception("Network error calling Suffolk API")
            return FilingAPIViews.error_response(f"Network error: {str(e)}", status_code=500)
        except Exception as e:
            logger.exception("Unexpected error")
            return FilingAPIViews.error_response(f"Error: {str(e)}", status_code=500)

    @staticmethod
    def convert_filing_data(filing):
        data = {}
        data["filing_status"] = filing.get("filingStatus").get("filingStatusCode")
        data["filing_status_text"] = next(iter(filing.get("filingStatus").get("statusDescriptionText"))).get("value")
        data["case_tracking_id"] = filing.get("caseTrackingID").get("value")
        data["filed_timestamp"] = filing.get("documentFiledDate").get("dateRepresentation").get("value").get("value")
        data["received_timestamp"] = (
            filing.get("documentReceivedDate").get("dateRepresentation").get("value").get("value")
        )
        for category in filing["documentCategoryText"]:
            if category["name"] == "{urn:tyler:ecf:extensions:Common}CaseTitle":
                data["case_title"] = category.get("value").get("value")
            if category["name"] == "{urn:tyler:ecf:extensions:Common}CaseNumber":
                data["case_number"] = category.get("value").get("value")
            if category["name"] == "{urn:tyler:ecf:extensions:Common}OrganizationIdentificationID":
                data["court_code"] = category.get("value").get("value")
            if category["name"] == "{urn:tyler:ecf:extensions:Common}FilingCode":
                data["filing_code"] = category.get("value").get("value")
        # TODO(brycew): submitted by?
        return data

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
    @require_http_methods(["POST"])
    @csrf_exempt
    def payment_fees(request):
        try:
            logger.info("Test in payment fees!")
            data = json.loads(request.body)
            efile_data = data.get("efile_data", {})
            if not efile_data:
                return JsonResponse({"success": False, "error": "No efile data provided in request"}, status=400)

            jurisdiction_id = request.session.get("jurisdiction")
            auth_tokens = request.session.get("auth_tokens", {})
            case_data = get_case_data(request, jurisdiction_id)
            court_id = case_data.get("court", "")
            url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction_id}/filingreview/courts/{court_id}/filing/fees"

            headers = get_headers()
            tyler_token = (
                auth_tokens.get(f"TYLER-TOKEN-{jurisdiction_id.upper()}")
                or auth_tokens.get(f"tyler_token_{jurisdiction_id}")
                or auth_tokens.get(f"tyler-token-{jurisdiction_id}")
            )

            # Add Tyler token if available (following auth_views.py pattern)
            if tyler_token:
                headers[f"TYLER-TOKEN-{jurisdiction_id.upper()}"] = tyler_token
            else:
                logger.warning(f"No Tyler token found for jurisdiction '{jurisdiction_id}' in filing submission")

            logger.info(f"Making request!: {url}")
            response = requests.post(url, json=efile_data, headers=headers)
            logger.info(f"Made request: {response.status_code}")

            if response.status_code == 200 or response.status_code == 201:
                response_data = response.json()

                logger.info(f"Sending back: {response_data}")
                return JsonResponse(
                    {
                        "success": True,
                        "message": "Payment fees submitted successfully",
                        "api_response": response_data,
                    }
                )
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("error", f"API returned status {response.status_code}")
                    logger.info(f"Sending back: {error_data}, {error_message}")

                    # For 400 errors, include more details
                    if response.status_code == 400:
                        validation_errors = error_data.get("validation_errors", error_data.get("errors", []))
                        if validation_errors:
                            error_message += f" - Validation errors: {validation_errors}"

                except json.JSONDecodeError:
                    error_message = f"API returned status {response.status_code} - Response: {response.text}"
                except Exception as parse_error:
                    error_message = (
                        f"API returned status {response.status_code} - Could not parse response: {str(parse_error)}"
                    )

                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Filing submission failed: {error_message}",
                        "api_status_code": response.status_code,
                        "api_response": response.text[:500] if response.text else "No response body",
                    },
                    status=response.status_code,
                )

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


# Individual view functions for URL mapping
get_filings = FilingAPIViews.get_filings
create_filing = FilingAPIViews.create_filing
payment_fees = FilingAPIViews.payment_fees
get_filing_detail = FilingAPIViews.get_filing_detail
update_filing = FilingAPIViews.update_filing
delete_filing = FilingAPIViews.delete_filing
