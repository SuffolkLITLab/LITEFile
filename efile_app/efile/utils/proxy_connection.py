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

