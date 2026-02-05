import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def auth_with_tyler_api(username, password, jurisdiction):
    url = f"{settings.EFSP_URL}/authenticate"
    try:
        api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)
        payload = {"api_key": api_key, f"tyler-{jurisdiction}": {"username": username, "password": password}}
        headers = {"Content-Type": "application/json", "User-Agent": f"{jurisdiction.title()}-eFile-Client/1.0"}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        logger.debug("Auth API response: status=%s url=%s", response.status_code, url)

        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.debug("Auth endpoint failed: %s - %s", url, str(e))

    return None


def get_party_type_code_from_api(court_code, case_type_code, jurisdiction, target_party_name=None):
    """
    Fetch party type codes from the Suffolk LIT Lab API and return the appropriate code.
    """
    try:
        path = f"/jurisdictions/{jurisdiction}/codes/courts/{court_code}/case_types/{case_type_code}/party_types"
        api_url = f"{settings.EFSP_URL}{path}"

        logger.debug(f"Fetching party types from: {api_url}")
        logger.debug(f"Looking for target party name: {target_party_name}")

        response = requests.get(api_url, timeout=10)

        if response.status_code == 200:
            party_types = response.json()
            logger.debug(f"API returned {len(party_types)} party types")

            if target_party_name:
                # Look for a specific party type by name (case-insensitive)
                target_lower = target_party_name.lower()
                for party_type in party_types:
                    if isinstance(party_type, dict) and "name" in party_type and "code" in party_type:
                        party_name_lower = party_type["name"].lower()
                        # Improved matching - check for exact words, not just substrings
                        if (
                            target_lower in party_name_lower
                            or party_name_lower in target_lower
                            or any(word in party_name_lower for word in target_lower.split())
                            or any(word in target_lower for word in party_name_lower.split())
                        ):
                            return party_type["code"]

            # If no specific match found, return the first available party type code
            if party_types and isinstance(party_types[0], dict) and "code" in party_types[0]:
                first_code = party_types[0]["code"]
                logger.info(
                    f"No specific match found, using first party type: "
                    f"{party_types[0].get('name', 'Unknown')} ({first_code})"
                )
                return first_code
        else:
            logger.error(f"API request failed with status: {response.status_code}")

    except Exception as e:
        logger.error(f"Failed to fetch party types from API: {e}")

    # Fallback to default codes if API call fails
    logger.warning("API call failed, returning None for fallback handling")
    return None


def get_headers():
    return {
        "Accept": "application/json",
        "User-Agent": "LITEfile-Client/1.0",
        "X-API-Key": getattr(settings, "SUFFOLK_EFILE_API_KEY", None),
    }
