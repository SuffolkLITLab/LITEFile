"""Originating case details for new appellate cases.

Massachusetts uses unpublished, environment-specific lower-court IDs maintained
by MACourts. Other jurisdictions use the EFSP's court location codes.
"""

import hashlib
import json
import logging
from pathlib import Path

import requests
from django.conf import settings
from django.core.cache import cache

from efile.services.court_selection import is_non_filing_court

logger = logging.getLogger(__name__)
LOWER_COURT_FIELDS = (
    "lower_court_code",
    "lower_court_name",
    "lower_court_prod_code",
    "lower_court_docket_number",
    "lower_court_title",
    "lower_court_judge",
)


def code_list(jurisdiction, path):
    url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/codes/{path}"
    key = "appeal-codes:" + hashlib.sha256(url.encode()).hexdigest()
    result = cache.get(key)
    if result is not None:
        return result if isinstance(result, list) else None
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        result = response.json()
        if isinstance(result, list):
            cache.set(key, result, 300)
            return result
    except (requests.RequestException, ValueError):
        logger.warning("Could not load appellate code list %s", url)
    # A single page consults this list for routing, validation, and its summary.
    # Briefly remember an outage so those checks do not each wait ten seconds.
    cache.set(key, False, 30)
    return None


def is_new_appeal(draft):
    if draft.existing_case != "new" or draft.previous_case_id or not draft.court_code or not draft.case_category_code:
        return False
    categories = code_list(draft.jurisdiction, f"courts/{draft.court_code}/categories")
    for category in categories or []:
        if isinstance(category, dict) and str(category.get("code")) == str(draft.case_category_code):
            return category.get("ecfcasetype") == "AppellateCase"
    # Keep the questions reachable during an outage, including for saved drafts.
    description = f"{draft.court_name} {draft.case_category_name}".lower()
    return any(word in description for word in ("appeal", "appellate", "supreme", "single justice"))


def lower_court_options(jurisdiction):
    if jurisdiction == "massachusetts":
        source = Path(__file__).resolve().parent.parent / "data" / "massachusetts_lower_courts.json"
        rows = json.loads(source.read_text())["courts"]
        return [
            {
                "value": row["tyler_lower_court_code"],
                "label": row["name"],
                "prod_code": row["tyler_prod_lower_court_code"],
            }
            for row in rows
        ]
    rows = code_list(jurisdiction, "courts/?fileable_only=false&with_names=true")
    return sorted(
        [
            {"value": str(row["code"]), "label": row["name"], "prod_code": str(row["code"])}
            for row in rows or []
            if isinstance(row, dict)
            and row.get("code")
            and row.get("name")
            and not is_non_filing_court(row["name"])
            and not any(word in row["name"].lower() for word in ("appellate", "appeals court", "supreme"))
        ],
        key=lambda row: row["label"],
    )


def appeal_questions(draft):
    if not is_new_appeal(draft):
        return []
    return [
        {
            "name": "lower_court_code",
            "label": "Lower court",
            "type": "select",
            "required": True,
            "options": lower_court_options(draft.jurisdiction),
        },
        {"name": "lower_court_docket_number", "label": "Lower court case number", "type": "text", "required": True},
        {"name": "lower_court_title", "label": "Lower court case caption", "type": "text", "required": True},
        {"name": "lower_court_judge", "label": "Lower court judge", "type": "text", "required": False},
    ]


def appeal_answers_complete(draft):
    questions = appeal_questions(draft)
    answers = draft.supplemental_fields or {}
    for question in questions:
        value = str(answers.get(question["name"]) or "").strip()
        if question["required"] and not value:
            return False
        if question["type"] == "select" and value not in {o["value"] for o in question["options"]}:
            return False
    return True
