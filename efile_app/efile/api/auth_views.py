"""
API views for authentication and user management
"""

import json
import logging

import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from requests.exceptions import RequestException, Timeout

from .base import APIResponseMixin

logger = logging.getLogger(__name__)


class AuthAPIViews(APIResponseMixin):
    """API views for authentication"""

    @staticmethod
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

    @staticmethod
    def get_tyler_token(request, state=None):
        """Helper method to retrieve Tyler token from various sources"""
        if state is None:
            state = AuthAPIViews.get_state_from_request(request)

        # Try user model first if authenticated
        if request.user.is_authenticated and hasattr(request.user, "tyler_token") and request.user.tyler_token:
            return request.user.tyler_token

        # Fallback to session
        auth_tokens = request.session.get("auth_tokens", {})
        logger.debug(f"Auth tokens in session: {auth_tokens}")

        # Try different Tyler token key formats
        tyler_token = (
            auth_tokens.get(f"TYLER-TOKEN-{state.upper()}")
            or auth_tokens.get(f"tyler_token_{state}")
            or auth_tokens.get(f"tyler-token-{state}")
        )

        return tyler_token

    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def user_login(request):
        """Handle user login with Django authentication"""
        try:
            data = json.loads(request.body)

            username = data.get("username")
            password = data.get("password")

            if not username or not password:
                return AuthAPIViews.error_response("Username and password required")

            # Use Django's authenticate which will try our custom backend
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)

                # Store user email in session for compatibility
                request.session["user_email"] = user.email

                return AuthAPIViews.success_response(
                    {
                        "user_id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "is_authenticated": True,
                        "has_suffolk_integration": bool(getattr(user, "suffolk_user_id", "")),
                    },
                    "Login successful",
                )
            else:
                return AuthAPIViews.error_response("Invalid credentials", 401)

        except json.JSONDecodeError:
            return AuthAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            logger.exception("Login error")
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def user_logout(request):
        """Handle user logout"""
        try:
            logout(request)
            # Clear session data but preserve CSRF token
            session_keys_to_keep = ["csrftoken"]
            session_data = {k: v for k, v in request.session.items() if k in session_keys_to_keep}
            request.session.clear()
            request.session.update(session_data)

            return AuthAPIViews.success_response({}, "Logout successful")
        except Exception as e:
            logger.exception("Logout error")
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def user_profile(request):
        """Get current user profile with integrated data"""
        try:
            if request.user.is_authenticated:
                # Use actual authenticated user data
                user = request.user

                user_data = {
                    # Django user data
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_authenticated": True,
                    "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    # Extended profile data (using clean User model extensions)
                    "address": user.address_line1,
                    "address_line2": user.address_line2,
                    "city": user.city,
                    "state": user.state,
                    "zip": user.zip_code,
                    "phone": user.phone,
                    "preferred_county": user.preferred_county,
                    "zip_code": user.zip_code,
                    # Firm information (using clean User model extensions)
                    "firm_name": user.firm_name,
                    "firm_id": user.firm_id,
                    "bar_number": user.bar_number,
                    # Location data
                    "location": {
                        "county": f"{user.preferred_county.title()} County" if user.preferred_county else "",
                        "state": "Illinois",
                        "zip_code": user.zip_code,
                        "available_counties": ["cook", "dupage", "kane", "lake", "mchenry", "will"],
                    },
                    # Suffolk integration status
                    "has_suffolk_integration": user.has_suffolk_integration,
                    "suffolk_user_id": user.suffolk_user_id,
                }

                # Try to enhance with live Suffolk API data if available
                try:
                    state = AuthAPIViews.get_state_from_request(request)
                    tyler_token = AuthAPIViews.get_tyler_token(request, state)

                    if tyler_token:
                        enhanced_data = AuthAPIViews._get_live_suffolk_data(state, tyler_token)
                        if enhanced_data:
                            user_data["external_firm_data"] = enhanced_data

                except Exception as e:
                    logger.debug("Could not enhance with live Suffolk data: %s", str(e))

                return AuthAPIViews.success_response(user_data)

            else:
                # Return demo data for unauthenticated users
                user_data = {
                    "id": None,
                    "username": "demo_user",
                    "email": "demo@example.com",
                    "first_name": "Demo",
                    "last_name": "User",
                    "is_authenticated": False,
                    "address": "123 Main St",
                    "address_line2": "",
                    "city": "Chicago",
                    "state": "IL",
                    "zip": "60601",
                    "phone": "(312) 555-1234",
                    "preferred_county": "cook",
                    "zip_code": "60601",
                    "location": {
                        "county": "Cook County",
                        "state": "Illinois",
                        "zip_code": "60601",
                        "available_counties": ["cook", "dupage", "kane", "lake", "mchenry", "will"],
                    },
                    "has_suffolk_integration": False,
                    "note": "Demo user - please log in for full functionality",
                }

                return AuthAPIViews.success_response(user_data)

        except Exception as e:
            logger.exception("User profile error")
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    def _get_live_suffolk_data(state, tyler_token):
        """Get live data from Suffolk API"""
        try:
            api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)

            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"{state.title()}-eFile-Client/1.0",
                "X-API-Key": api_key if api_key else "",
                f"tyler-token-{state}": tyler_token,
            }

            url = f"{settings.EFSP_URL}/jurisdictions/{state}/firmattorneyservice/firm"
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                return response.json()

        except Exception as e:
            logger.debug("Live Suffolk API call failed: %s", str(e))

        return None

    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def external_auth(request):
        """Handle authentication with external Suffolk eFile API"""
        try:
            data = json.loads(request.body)

            username = data.get("username")
            password = data.get("password")

            if not username or not password:
                return AuthAPIViews.error_response("Username and password required")

            # This now uses Django's authenticate which will use our custom backend
            user = authenticate(request, username=username, password=password)

            if user:
                login(request, user)

                state = AuthAPIViews.get_state_from_request(request)
                tyler_token = AuthAPIViews.get_tyler_token(request, state)

                return AuthAPIViews.success_response(
                    {
                        "authenticated": True,
                        "user": {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "first_name": user.first_name,
                            "last_name": user.last_name,
                        },
                        "state": state,
                        "has_tyler_token": bool(tyler_token),
                        "is_authenticated": True,
                    },
                    "External authentication successful",
                )
            else:
                return AuthAPIViews.error_response("External authentication failed", 401)

        except json.JSONDecodeError:
            return AuthAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            logger.exception("External auth error")
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def external_profile(request):
        """Get additional profile data from external sources"""
        try:
            if not request.user.is_authenticated:
                return AuthAPIViews.error_response("Not authenticated", 401)

            # Enhanced location data based on user's actual profile
            user = request.user

            external_data = {
                "location_details": {
                    "county_court_info": {
                        "cook": {"address": "50 W Washington St, Chicago, IL", "phone": "(312) 603-5030"},
                        "dupage": {"address": "505 N County Farm Rd, Wheaton, IL", "phone": "(630) 407-8700"},
                        "kane": {"address": "37W777 Route 38, St Charles, IL", "phone": "(630) 232-3413"},
                    }
                },
                "preferences": {
                    "language": getattr(user.profile, "language", "en") if hasattr(user, "profile") else "en",
                    "timezone": getattr(user.profile, "timezone", "America/Chicago")
                    if hasattr(user, "profile")
                    else "America/Chicago",
                    "notification_settings": {
                        "email": getattr(user.profile, "email_notifications", True)
                        if hasattr(user, "profile")
                        else True,
                        "sms": getattr(user.profile, "sms_notifications", False) if hasattr(user, "profile") else False,
                    },
                },
                "user_county": getattr(user, "preferred_county", "cook"),
            }

            return AuthAPIViews.success_response(external_data)

        except Exception as e:
            logger.exception("External profile error")
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def tyler_token(request):
        """Get Tyler token and API key for external form submissions"""
        try:
            # Get state and Tyler token dynamically
            state = AuthAPIViews.get_state_from_request(request)
            tyler_token = AuthAPIViews.get_tyler_token(request, state)
            api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)

            return AuthAPIViews.success_response(
                {
                    "tyler_token": tyler_token,
                    "api_key": api_key,
                    "state": state,
                    "is_authenticated": request.user.is_authenticated,
                }
            )
        except Exception as e:
            logger.exception("Tyler token error")
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def payment_accounts(request):
        """Get payment accounts from Suffolk eFile API with proper authentication"""
        try:
            # Get state and Tyler token dynamically
            state = AuthAPIViews.get_state_from_request(request)
            tyler_token = AuthAPIViews.get_tyler_token(request, state)
            api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)

            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"{state.title()}-eFile-Client/1.0",
                "X-API-Key": api_key if api_key else "",
            }

            # Add Tyler token if available
            if tyler_token:
                headers[f"tyler-token-{state}"] = tyler_token
            else:
                logger.info(
                    "No Tyler token found for state '%s' in Suffolk eFile payment accounts request",
                    state,
                )

            url = f"{settings.EFSP_URL}/jurisdictions/{state}/payments/payment-accounts/"
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
            logger.exception("Payment accounts error")
            return AuthAPIViews.error_response(f"Error: {str(e)}")


# Individual view functions for URL mapping
user_login = AuthAPIViews.user_login
user_logout = AuthAPIViews.user_logout
user_profile = AuthAPIViews.user_profile
external_auth = AuthAPIViews.external_auth
external_profile = AuthAPIViews.external_profile
payment_accounts = AuthAPIViews.payment_accounts
tyler_token = AuthAPIViews.tyler_token
