"""
Authentication backends for eFile system
"""

import logging

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)
User = get_user_model()


class SuffolkEFileBackend(BaseBackend):
    """
    Authentication backend that integrates with Suffolk eFile API
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user against Suffolk eFile API and create/update Django user
        """
        if not username or not password:
            return None

        try:
            # Get state from request or default to Illinois
            state = self._get_state_from_request(request)

            # Authenticate with Suffolk eFile API
            auth_data = self._authenticate_with_suffolk_api(username, password, state)

            if not auth_data:
                logger.info("Suffolk API authentication failed for user: %s", username)
                return None

            # Get or create Django user
            user = self._get_or_create_user(username, auth_data, state)

            # Update user profile with latest data
            self._update_user_profile(user, auth_data, state)

            # Store tokens in session
            if request:
                self._store_tokens_in_session(request, auth_data, state)

            logger.info("Successfully authenticated user: %s", username)
            return user

        except Exception:
            logger.exception("Error during authentication for user: %s", username)
            return None

    def get_user(self, user_id):
        """
        Get user by ID
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def _get_state_from_request(self, request):
        """Extract state from request"""
        if not request:
            return "illinois"

        # Try query parameters
        state = request.GET.get("state")
        if state:
            return state.lower()

        # Try URL path
        path = request.path
        if "/jurisdictions/" in path:
            path_parts = path.split("/jurisdictions/")
            if len(path_parts) > 1:
                state_part = path_parts[1].split("/")[0]
                if state_part:
                    return state_part.lower()

        return "illinois"

    def _authenticate_with_suffolk_api(self, username, password, state):
        """
        Authenticate with Suffolk eFile API
        """
        try:
            api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)
            efsp_url = getattr(settings, "EFSP_URL", "https://api.suffolk.edu/efsp")

            # Try multiple authentication endpoints
            auth_endpoints = [f"{efsp_url}/jurisdictions/{state}/auth/login", f"{efsp_url}/authenticate"]

            for url in auth_endpoints:
                try:
                    if "authenticate" in url:
                        # Legacy endpoint format
                        payload = {
                            "api_key": api_key,
                            f"tyler-{state}": {
                                "username": username,
                                "password": password,
                            },
                        }
                    else:
                        # Standard endpoint format
                        payload = {"username": username, "password": password}

                    headers = {"Content-Type": "application/json", "User-Agent": f"{state.title()}-eFile-Client/1.0"}

                    if api_key and "authenticate" not in url:
                        headers["X-API-Key"] = api_key

                    response = requests.post(url, json=payload, headers=headers, timeout=10)

                    logger.debug("Auth API response: status=%s url=%s", response.status_code, url)

                    if response.status_code == 200:
                        return response.json()

                except RequestException as e:
                    logger.debug("Auth endpoint failed: %s - %s", url, str(e))
                    continue

            return None

        except Exception:
            logger.exception("Suffolk API authentication error")
            return None

    def _get_or_create_user(self, username, auth_data, state):
        """
        Get existing user or create new one
        """
        # Look for existing user by username or email
        user = None

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            try:
                user = User.objects.get(email=username)
            except User.DoesNotExist:
                pass

        if not user:
            # Create new user
            user_data = self._extract_user_data(auth_data, username, state)

            user = User.objects.create_user(
                username=username,
                email=user_data.get("email", username),
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name", ""),
            )

            logger.info("Created new user: %s", username)

        return user

    def _extract_user_data(self, auth_data, username, state):
        """
        Extract user data from Suffolk API response
        """
        user_data = {
            "email": username,
            "first_name": "",
            "last_name": "",
        }

        # Extract from various possible response structures
        if "user" in auth_data:
            user_info = auth_data["user"]
            user_data.update(
                {
                    "first_name": user_info.get("firstName", user_info.get("first_name", "")),
                    "last_name": user_info.get("lastName", user_info.get("last_name", "")),
                    "email": user_info.get("email", username),
                }
            )

        return user_data

    def _update_user_profile(self, user, auth_data, state):
        """
        Update user profile with latest data from API using existing model structure
        """
        try:
            from .models import update_user_suffolk_data

            update_user_suffolk_data(user, auth_data, state)

        except Exception:
            logger.exception("Error updating user profile")

    def _store_tokens_in_session(self, request, auth_data, state):
        """
        Store authentication tokens in session
        """
        try:
            auth_tokens = {
                "access_token": auth_data.get("access_token"),
                "refresh_token": auth_data.get("refresh_token"),
                "expires_in": auth_data.get("expires_in"),
                "state": state,
            }

            # Add Tyler token
            tyler_token_key = f"tyler_token_{state}"
            if tyler_token_key in auth_data:
                auth_tokens[tyler_token_key] = auth_data[tyler_token_key]
                auth_tokens[f"TYLER-TOKEN-{state.upper()}"] = auth_data[tyler_token_key]

            request.session["auth_tokens"] = auth_tokens

        except Exception:
            logger.exception("Error storing tokens in session")
