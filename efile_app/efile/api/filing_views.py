"""
API views for filing operations and document management
"""

import json
import logging

import requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .base import APIResponseMixin, get_auth_tokens

logger = logging.getLogger(__name__)


class FilingAPIViews(APIResponseMixin):
    """API views for filing operations"""

    @staticmethod
    @require_http_methods(["GET"])
    def get_filings(request):
        """Get user's filings"""
        try:
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)

            # API call to get user's filings
            api_url = "https://suffolkefile.com/api/filings"
            headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
            logger.debug("GET %s header keys=%s", api_url, list(headers.keys()))
            response = requests.get(api_url, headers=headers, timeout=30)
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
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)

            data = json.loads(request.body)

            # Validate required fields
            required_fields = ["case_category", "case_type", "filing_type", "county"]
            missing_fields = [field for field in required_fields if not data.get(field)]

            if missing_fields:
                return FilingAPIViews.error_response(f"Missing required fields: {', '.join(missing_fields)}")

            # API call to create filing
            api_url = "https://suffolkefile.com/api/filings"
            headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
            logger.debug("POST %s header keys=%s payload keys=%s", api_url, list(headers.keys()), list(data.keys()))
            response = requests.post(api_url, json=data, headers=headers, timeout=30)
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
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)

            # API call to get filing details
            api_url = f"https://suffolkefile.com/api/filings/{filing_id}"
            headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
            logger.debug("GET %s header keys=%s", api_url, list(headers.keys()))
            response = requests.get(api_url, headers=headers, timeout=30)
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
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)

            data = json.loads(request.body)

            # API call to update filing
            api_url = f"https://suffolkefile.com/api/filings/{filing_id}"
            headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
            logger.debug("PUT %s header keys=%s payload keys=%s", api_url, list(headers.keys()), list(data.keys()))
            response = requests.put(api_url, json=data, headers=headers, timeout=30)
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
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)

            # API call to delete filing
            api_url = f"https://suffolkefile.com/api/filings/{filing_id}"
            headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
            logger.debug("DELETE %s header keys=%s", api_url, list(headers.keys()))
            response = requests.delete(api_url, headers=headers, timeout=30)
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
get_filing_detail = FilingAPIViews.get_filing_detail
update_filing = FilingAPIViews.update_filing
delete_filing = FilingAPIViews.delete_filing
