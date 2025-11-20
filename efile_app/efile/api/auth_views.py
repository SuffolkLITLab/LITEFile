"""
API views for authentication and user management
"""

import json
import logging

import requests
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from requests.exceptions import RequestException, Timeout

from efile.api.suffolk_api_views import get_tyler_token
from efile.utils.jurisdiction_stuff import get_jurisdiction_from_request

from .base import APIResponseMixin

logger = logging.getLogger(__name__)


class AuthAPIViews(APIResponseMixin):
    """API views for authentication"""

    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def user_login(request):
        """Handle user login"""
        try:
            data = json.loads(request.body)

            username = data.get("username")
            password = data.get("password")
            jurisdiction = data.get("jurisdiction")

            if not username or not password or not jurisdiction:
                return AuthAPIViews.error_response("Username, password, and jurisdiction required")

            user = authenticate(request, username=username, password=password, jurisdiction=jurisdiction)

            if user is not None:
                login(request, user)
                return AuthAPIViews.success_response(
                    {"user_id": user.id, "username": user.username, "email": user.email, "is_authenticated": True},
                    "Login successful",
                )
            else:
                return AuthAPIViews.error_response("Invalid credentials", 401)

        except json.JSONDecodeError as e:
            return AuthAPIViews.error_response(f"Invalid JSON data: {str(e)}, {request.body}")
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def user_logout(request):
        """Handle user logout"""
        from efile.authentication import SuffolkEFileBackend

        try:
            SuffolkEFileBackend.logout(request)
            return AuthAPIViews.success_response({}, "Logout successful")
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def user_profile(request):
        """Get current user profile from external Suffolk eFile API"""
        try:
            # TODO(brycew): get some of this from the existing logged in user
            # Get jurisdiction and Tyler token dynamically
            jurisdiction = get_jurisdiction_from_request(request)
            tyler_token = get_tyler_token(request, jurisdiction)
            api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)

            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"{jurisdiction.title()}-eFile-Client/1.0",
                "X-API-Key": api_key if api_key else "",
            }

            # Add Tyler token if available
            if tyler_token:
                headers[f"tyler-token-{jurisdiction}"] = tyler_token
            else:
                # Log that no token was found for debugging
                logger.info("No Tyler token found for state '%s' in Suffolk eFile API request", jurisdiction)

            if request.user.tyler_user_id:
                headers[f"TYLER-ID-{jurisdiction.upper()}"] = request.user.tyler_user_id

            url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/firmattorneyservice/firm"
            logger.debug("GET %s header keys=%s", url, list(headers.keys()))
            api_response = requests.get(url, headers=headers, timeout=10)
            logger.debug(
                "User profile response: status=%s content_type=%s",
                api_response.status_code,
                api_response.headers.get("Content-Type"),
            )

            self_url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/adminusers/user"
            self_response = requests.get(self_url, headers=headers, timeout=10)

            logger.debug(
                "self profile response: status=%s text=%s content_type=%s",
                self_response.status_code,
                self_response.text,
                self_response.headers.get("Content-Type"),
            )

            if api_response.status_code == 200 and self_response.status_code == 200:
                external_data = api_response.json()
                self_json = self_response.json()
                logger.debug("self_json: %s", self_json)

                # Extract address information from external API response
                address_info = external_data.get("address", {})
                address_line1 = address_info.get("addressLine1", "")
                address_line2 = address_info.get("addressLine2", "")
                city = address_info.get("city", "")
                state = address_info.get("state", "IL")
                zip_code = address_info.get("zipCode", "60601")
                phone_number = external_data.get("phoneNumber", "")

                # Build user profile data combining local and external data
                user_data = {
                    "external_firm_data": external_data,
                    # Local user data (if authenticated)
                    "id": request.user.id if request.user.is_authenticated else None,
                    "username": request.user.username if request.user.is_authenticated else "guest",
                    "email": request.user.email if request.user.is_authenticated else request.session.get("user_email"),
                    "first_name": self_json["firstName"],
                    "last_name": self_json["lastName"],
                    "date_joined": request.user.date_joined.isoformat() if request.user.is_authenticated else None,
                    "last_login": request.user.last_login.isoformat()
                    if (request.user.is_authenticated and request.user.last_login)
                    else None,
                    # Address information from external API
                    "address": address_line1,
                    "address_line2": address_line2,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                    "phone": phone_number,
                    # Default location information
                    "preferred_county": "cook",
                    "zip_code": zip_code,  # Use actual zip from API
                    "location": {
                        "county": "Cook County",
                        "state": "Illinois",
                        "zip_code": zip_code,
                        "available_counties": ["cook", "dupage", "kane", "lake", "mchenry", "will"],
                    },
                }

                return AuthAPIViews.success_response(user_data)
            else:
                return AuthAPIViews.error_response("Unable to retrieve profile", 500)
        except Timeout:
            return AuthAPIViews.error_response("External API request timed out", 408)
        except Exception:
            logger.exception("Request exception")
            return AuthAPIViews.error_response("Request Exception", 500)

    @staticmethod
    @require_http_methods(["GET"])
    def external_profile(request):
        """Get additional profile data from external sources"""
        try:
            if not request.user.is_authenticated:
                return AuthAPIViews.error_response("Not authenticated", 401)

            # This could fetch additional data from Suffolk eFile API or other sources
            # For now, return enhanced location data
            external_data = {
                "location_details": {
                    "county_court_info": {
                        "cook": {"address": "50 W Washington St, Chicago, IL", "phone": "(312) 603-5030"},
                        "dupage": {"address": "505 N County Farm Rd, Wheaton, IL", "phone": "(630) 407-8700"},
                        "kane": {"address": "37W777 Route 38, St Charles, IL", "phone": "(630) 232-3413"},
                    }
                },
                "preferences": {
                    "language": "en",
                    "timezone": "America/Chicago",
                    "notification_settings": {"email": True, "sms": False},
                },
            }

            return AuthAPIViews.success_response(external_data)

        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def tyler_token(request):
        """Get Tyler token and API key for external form submissions"""
        try:
            # Get jurisdiction and Tyler token dynamically
            jurisdiction = get_jurisdiction_from_request(request)
            tyler_token = get_tyler_token(request, jurisdiction)
            api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)

            return AuthAPIViews.success_response(
                {"tyler_token": tyler_token, "api_key": api_key, "state": jurisdiction}
            )
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def payment_accounts(request):
        """Get payment accounts from Suffolk eFile API with proper authentication"""
        try:
            # Get jurisdiction and Tyler token dynamically
            jurisdiction = get_jurisdiction_from_request(request)
            tyler_token = get_tyler_token(request, jurisdiction)
            api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)

            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"{jurisdiction.title()}-eFile-Client/1.0",
                "X-API-Key": api_key if api_key else "",
            }

            # Add Tyler token if available
            if tyler_token:
                headers[f"tyler-token-{jurisdiction}"] = tyler_token
            else:
                # Log that no token was found for debugging
                logger.info(
                    "No Tyler token found for state '%s' in Suffolk eFile payment accounts request",
                    jurisdiction,
                )

            url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/payments/payment-accounts/"
            logger.debug("GET %s header keys=%s", url, list(headers.keys()))
            api_response = requests.get(url, headers=headers, timeout=10)
            logger.debug(
                "Payment accounts response: status=%s content_type=%s",
                api_response.status_code,
                api_response.headers.get("Content-Type"),
            )

            if api_response.status_code == 200:
                payment_accounts = api_response.json()
                return AuthAPIViews.success_response(payment_accounts)
            elif api_response.status_code == 401:
                # Return empty list for unauthorized - frontend will show "add new payment method"
                return AuthAPIViews.success_response([])
            else:
                # Return error with status info
                return AuthAPIViews.error_response(
                    f"Payment accounts API returned status {api_response.status_code}: {api_response.text[:200]}",
                    api_response.status_code,
                )

        except Timeout:
            return AuthAPIViews.error_response("Payment accounts API request timed out", 408)
        except RequestException as e:
            return AuthAPIViews.error_response(f"Could not connect to payment accounts API: {str(e)}", 503)
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")


# Individual view functions for URL mapping
user_login = AuthAPIViews.user_login
user_logout = AuthAPIViews.user_logout
user_profile = AuthAPIViews.user_profile
external_profile = AuthAPIViews.external_profile
payment_accounts = AuthAPIViews.payment_accounts
tyler_token = AuthAPIViews.tyler_token
