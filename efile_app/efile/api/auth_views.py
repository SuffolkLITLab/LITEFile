"""
API views for authentication and user management
"""

import json

import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from requests.exceptions import RequestException, Timeout

from .base import APIResponseMixin


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

        auth_tokens = request.session.get("auth_tokens", {})
        print(f"Auth tokens in session: {auth_tokens}")

        # Try different Tyler token key formats
        tyler_token = (
            auth_tokens.get(f"TYLER-TOKEN-{state.upper()}")
            or auth_tokens.get(f"tyler_token_{state}")
            or auth_tokens.get(f"tyler-token-{state}")
        )

        if tyler_token:
            return tyler_token

        return None

    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def user_login(request):
        """Handle user login"""
        try:
            data = json.loads(request.body)

            username = data.get("username")
            password = data.get("password")

            if not username or not password:
                return AuthAPIViews.error_response("Username and password required")

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return AuthAPIViews.success_response(
                    {"user_id": user.id, "username": user.username, "email": user.email}, "Login successful"
                )
            else:
                return AuthAPIViews.error_response("Invalid credentials", 401)

        except json.JSONDecodeError:
            return AuthAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def user_logout(request):
        """Handle user logout"""
        try:
            logout(request)
            return AuthAPIViews.success_response({}, "Logout successful")
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")

    @staticmethod
    @require_http_methods(["GET"])
    def user_profile(request):
        """Get current user profile from external Suffolk eFile API"""
        try:
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
                    # Log that no token was found for debugging
                    print(f"Warning: No Tyler token found for state '{state}' in Suffolk eFile API request")

                api_response = requests.get(
                    f"https://efile-test.suffolklitlab.org/jurisdictions/{state}/firmattorneyservice/firm",
                    headers=headers,
                    timeout=10,
                )

                if api_response.status_code == 200:
                    external_data = api_response.json()
                    print(f"External data retrieved: {external_data}")

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
                        "email": request.user.email
                        if request.user.is_authenticated
                        else request.session.get("user_email"),
                        "first_name": request.user.first_name if request.user.is_authenticated else "Demo",
                        "last_name": request.user.last_name if request.user.is_authenticated else "User",
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
                elif api_response.status_code == 401:
                    # API requires authentication - return mock data for demo
                    user_data = {
                        "external_api_status": "requires_authentication",
                        "note": "Suffolk eFile API requires authentication. Using demo data.",
                        "id": request.user.id if request.user.is_authenticated else None,
                        "username": request.user.username if request.user.is_authenticated else "demo_user",
                        "email": request.user.email
                        if request.user.is_authenticated
                        else request.session.get("user_email", "demo@example.com"),
                        "first_name": request.user.first_name if request.user.is_authenticated else "John",
                        "last_name": request.user.last_name if request.user.is_authenticated else "Doe",
                        # Default address information for demo
                        "address": "123 Main St",
                        "address_line2": "",
                        "city": "Chicago",
                        "state": "IL",
                        "zip": "60601",
                        "phone": "(312) 555-1234",
                        "preferred_county": "cook",
                        "zip_code": "60601",  # Downtown Chicago zip for demo
                        "location": {
                            "county": "Cook County",
                            "state": "Illinois",
                            "zip_code": "60601",
                            "available_counties": ["cook", "dupage", "kane", "lake", "mchenry", "will"],
                        },
                        # Mock firm data based on Suffolk eFile API structure
                        "firm_info": {
                            "firm_name": "Demo Law Firm",
                            "firm_id": "DEMO_001",
                            "attorneys": [
                                {
                                    "attorney_id": "ATT_001",
                                    "first_name": "John",
                                    "last_name": "Doe",
                                    "bar_number": "123456",
                                    "email": "john.doe@demolaw.com",
                                }
                            ],
                        },
                    }

                    return AuthAPIViews.success_response(user_data)
                else:
                    # Fall back to local data if external API fails
                    user_data = {
                        "external_api_error": f"Suffolk API returned status {api_response.status_code}",
                        "response_text": api_response.text[:200] if api_response.text else "No response body",
                        "id": request.user.id if request.user.is_authenticated else None,
                        "username": request.user.username if request.user.is_authenticated else "guest",
                        "email": request.user.email
                        if request.user.is_authenticated
                        else request.session.get("user_email"),
                        "first_name": request.user.first_name if request.user.is_authenticated else "Demo",
                        "last_name": request.user.last_name if request.user.is_authenticated else "User",
                        # Default address information
                        "address": "123 Main St",
                        "address_line2": "",
                        "city": "Chicago",
                        "state": "IL",
                        "zip": "60601",
                        "phone": "(312) 555-1234",
                        "preferred_county": "cook",
                        "zip_code": "60601",  # Downtown Chicago zip for demo
                        "location": {"county": "Cook County", "state": "Illinois", "zip_code": "60601"},
                    }

                    return AuthAPIViews.success_response(user_data)

            except Timeout:
                return AuthAPIViews.error_response("External API request timed out", 408)
            except RequestException as e:
                # Fall back to local data if external API is unavailable
                user_data = {
                    "external_api_error": f"Could not connect to Suffolk API: {str(e)}",
                    "id": request.user.id if request.user.is_authenticated else None,
                    "username": request.user.username if request.user.is_authenticated else "guest",
                    "email": request.user.email if request.user.is_authenticated else request.session.get("user_email"),
                    "first_name": request.user.first_name if request.user.is_authenticated else "Demo",
                    "last_name": request.user.last_name if request.user.is_authenticated else "User",
                    # Default address information
                    "address": "123 Main St",
                    "address_line2": "",
                    "city": "Chicago",
                    "state": "IL",
                    "zip": "60601",
                    "phone": "(312) 555-1234",
                    "preferred_county": "cook",
                    "zip_code": "60601",  # Downtown Chicago zip for demo
                    "location": {"county": "Cook County", "state": "Illinois", "zip_code": "60601"},
                }

                return AuthAPIViews.success_response(user_data)

        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")

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

            # Authenticate with Suffolk eFile API
            state = AuthAPIViews.get_state_from_request(request)
            auth_response = requests.post(
                f"https://efile-test.suffolklitlab.org/jurisdictions/{state}/auth/login",
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json", "User-Agent": f"{state.title()}-eFile-Client/1.0"},
            )

            if auth_response.status_code == 200:
                auth_data = auth_response.json()

                # Store auth tokens in session including Tyler token
                request.session["auth_tokens"] = {
                    "access_token": auth_data.get("access_token"),
                    "refresh_token": auth_data.get("refresh_token"),
                    f"tyler_token_{state}": auth_data.get(f"tyler_token_{state}"),
                    "expires_in": auth_data.get("expires_in"),
                    "state": state,  # Store the state for future reference
                }

                return AuthAPIViews.success_response(
                    {
                        "authenticated": True,
                        "user": auth_data.get("user", {}),
                        "state": state,
                        "has_tyler_token": f"tyler_token_{state}" in auth_data,
                    },
                    "External authentication successful",
                )
            else:
                return AuthAPIViews.error_response("External authentication failed", 401)

        except json.JSONDecodeError:
            return AuthAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            return AuthAPIViews.error_response(f"Error: {str(e)}")

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
            # Get state and Tyler token dynamically
            state = AuthAPIViews.get_state_from_request(request)
            tyler_token = AuthAPIViews.get_tyler_token(request, state)
            api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)

            return AuthAPIViews.success_response({"tyler_token": tyler_token, "api_key": api_key, "state": state})
        except Exception as e:
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
                # Log that no token was found for debugging
                print(f"Warning: No Tyler token found for state '{state}' in Suffolk eFile payment accounts request")

            api_response = requests.get(
                f"https://efile-test.suffolklitlab.org/jurisdictions/{state}/payments/payment-accounts/",
                headers=headers,
                timeout=10,
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
external_auth = AuthAPIViews.external_auth
external_profile = AuthAPIViews.external_profile
payment_accounts = AuthAPIViews.payment_accounts
tyler_token = AuthAPIViews.tyler_token
