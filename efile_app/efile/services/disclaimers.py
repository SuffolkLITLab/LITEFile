"""Read court requirements and bind acceptance to the text shown on Review."""

from urllib.parse import quote

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils import timezone

# Review may show text this old; submit always rechecks it against the court.
DISCLAIMER_TTL_SECONDS = 600


class DisclaimerUnavailable(ValueError):
    pass


def _unescape(text):
    # Some proxy code tables contain literal backslash escapes inside the JSON
    # string, including quotes around link attributes and paragraph separators.
    return text.replace('\\"', '"').replace("\\n", "\n")


def court_disclaimers(draft, *, fresh=False):
    """The court's requirements, from cache unless ``fresh``; a fresh fetch refreshes the cache."""
    if not draft.court_code:
        raise DisclaimerUnavailable("Choose a court to see its filing requirements.")
    path = f"{quote(draft.jurisdiction, safe='')}/codes/courts/{quote(draft.court_code, safe='')}"
    cache_key = f"court-disclaimers:{path}"
    if not fresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    url = f"{settings.EFSP_URL}/jurisdictions/{path}/disclaimer_requirements"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("Expected a list")
        requirements = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("code") or not isinstance(row.get("requirementText"), str):
                raise ValueError("Invalid court requirement")
            text = _unescape(row["requirementText"])
            if not text.strip():
                raise ValueError("Empty court requirement")
            requirements.append(
                {
                    "code": str(row["code"]),
                    "name": str(row.get("name") or ""),
                    "text": text,
                    "order": int(row.get("listorder") or 0),
                }
            )
        requirements.sort(key=lambda item: (item["order"], item["code"]))
    except (requests.RequestException, ValueError, TypeError) as error:
        raise DisclaimerUnavailable(
            "We could not load the court's filing requirements. Reload this page to try again."
        ) from error
    cache.set(cache_key, requirements, DISCLAIMER_TTL_SECONDS)
    return requirements


def _agreement(draft, requirements):
    return {
        "draft": str(draft.pk),
        "jurisdiction": draft.jurisdiction,
        "court": draft.court_code,
        "requirements": requirements,
    }


def disclaimer_context(draft):
    try:
        requirements = court_disclaimers(draft)
    except DisclaimerUnavailable as error:
        # An absent agreement token, not a credential.
        return {"disclaimer_error": str(error), "disclaimer_token": ""}  # nosec B105
    return {
        "court_disclaimers": requirements,
        "disclaimer_token": signing.dumps(_agreement(draft, requirements), salt="court-disclaimers"),
    }


def validate_acceptance(draft, payload):
    """Recheck the current court text; a stale page cannot accept changed requirements."""
    requirements = court_disclaimers(draft, fresh=True)
    agreement = _agreement(draft, requirements)
    try:
        accepted = signing.loads(payload.get("disclaimer_token", ""), salt="court-disclaimers")
    except (signing.BadSignature, TypeError):
        accepted = None
    if payload.get("confirm_submission") is not True or accepted != agreement:
        raise ValueError("Review and accept the current court requirements. Reload the review page to continue.")
    return {**agreement, "accepted_at": timezone.now().isoformat(), "user_id": str(draft.user_id)}
