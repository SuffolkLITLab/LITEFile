"""Authenticated payment accounts, including user-requested managed waivers."""

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

MANAGED_WAIVER_NAME = "LITEFile managed waiver account"


def account_headers(jurisdiction, token):
    return {
        "X-API-Key": getattr(settings, "SUFFOLK_EFILE_API_KEY", "") or "",
        f"tyler-token-{jurisdiction}": token,
    }


def is_active(account):
    # Tyler sends Active as a JAXB element ({"value": true, ...}), not a bare boolean.
    active = account.get("active", True)
    if isinstance(active, dict):
        active = active.get("value", True)
    return active not in (False, "false")


def payment_accounts(jurisdiction, token):
    response = requests.get(
        f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/payments/payment-accounts/",
        headers=account_headers(jurisdiction, token),
        timeout=10,
    )
    response.raise_for_status()
    accounts = response.json()
    if not isinstance(accounts, list):
        raise ValueError("Invalid payment account list")
    return [
        account
        for account in accounts
        if isinstance(account, dict) and account.get("paymentAccountID") and is_active(account)
    ]


def ensure_waiver_account(user, jurisdiction, token, preferred_id=""):
    # Serialize requests by this user, including requests from other drafts/tabs.
    # Always re-read Tyler before creating; failed reads must never mean no account.
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        waivers = [a for a in payment_accounts(jurisdiction, token) if a.get("paymentAccountTypeCode") == "WV"]
        if waivers:
            return next((a for a in waivers if str(a["paymentAccountID"]) == preferred_id), waivers[0])
        response = requests.post(
            f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/payments/payment-accounts",
            data=MANAGED_WAIVER_NAME,
            headers={**account_headers(jurisdiction, token), "Content-Type": "text/plain"},
            timeout=20,
        )
        response.raise_for_status()
        try:
            account_id = response.json()
        except ValueError:
            account_id = response.text
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("Missing waiver account ID")
        return {
            "paymentAccountID": account_id.strip(),
            "accountName": MANAGED_WAIVER_NAME,
            "paymentAccountTypeCode": "WV",
        }
