"""Read court requirements and bind acceptance to the text shown on Review."""

from urllib.parse import quote

import requests
from django.conf import settings
from django.core import signing
from django.utils import timezone


class DisclaimerUnavailable(ValueError):
    pass


def court_disclaimers(draft):
    if not draft.court_code:
        raise DisclaimerUnavailable("Choose a court to see its filing requirements.")
    url = (
        f"{settings.EFSP_URL}/jurisdictions/{quote(draft.jurisdiction, safe='')}/codes/courts/"
        f"{quote(draft.court_code, safe='')}/disclaimer_requirements"
    )
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
            if not row["requirementText"].strip():
                raise ValueError("Empty court requirement")
            requirements.append(
                {
                    "code": str(row["code"]),
                    "name": str(row.get("name") or ""),
                    "text": row["requirementText"],
                    "order": int(row.get("listorder") or 0),
                }
            )
        return sorted(requirements, key=lambda item: (item["order"], item["code"]))
    except (requests.RequestException, ValueError, TypeError) as error:
        raise DisclaimerUnavailable(
            "We could not load the court's filing requirements. Reload this page to try again."
        ) from error


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
    requirements = court_disclaimers(draft)
    agreement = _agreement(draft, requirements)
    try:
        accepted = signing.loads(payload.get("disclaimer_token", ""), salt="court-disclaimers")
    except (signing.BadSignature, TypeError):
        accepted = None
    if payload.get("confirm_submission") is not True or accepted != agreement:
        raise ValueError("Review and accept the current court requirements. Reload the review page to continue.")
    return {**agreement, "accepted_at": timezone.now().isoformat(), "user_id": str(draft.user_id)}
