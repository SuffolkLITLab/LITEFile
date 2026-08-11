from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.utils.config_loader import config_loader
from efile.workflow import ExistingCase

logger = logging.getLogger(__name__)

# Keywords matched against a court's own party-type names (e.g.
# "Plaintiff/Petitioner") to turn a case-posture guess into one of that
# court's actual codes.
_INITIATING_PARTY_KEYWORDS = ("plaintiff", "petitioner")
_RESPONDING_PARTY_KEYWORDS = ("defendant", "respondent")


def party_is_complete(party: FilingParty) -> bool:
    has_name = bool(party.organization_name or (party.first_name and party.last_name))
    has_address = bool(party.address_line_1 and party.city and party.state and party.zip_code)
    return bool(party.party_type and has_name and has_address)


def incomplete_parties(draft: FilingDraft):
    return [party for party in FilingParty.objects.filter(draft=draft) if not party_is_complete(party)]


def get_party_types(draft: FilingDraft) -> list[dict[str, Any]]:
    if not draft.court_code or not draft.case_type_code:
        return []
    url = (
        f"{settings.EFSP_URL}/jurisdictions/{draft.jurisdiction}/codes/courts/"
        f"{draft.court_code}/case_types/{draft.case_type_code}/party_types"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("Could not load party types for draft %s", draft.pk)
        return []
    if not isinstance(data, list):
        return []
    return [
        {
            "code": str(item.get("code") or ""),
            "name": str(item.get("name") or ""),
            "required": str(item.get("isrequired", "")).lower() == "true" or item.get("isrequired") is True,
        }
        for item in data
        if isinstance(item, dict) and item.get("code") and item.get("name")
    ]


def guess_filer_party_type(draft: FilingDraft, party_types: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Suggest the filer's role from case posture alone -- never authoritative.

    A brand new case is almost always opened by the plaintiff/petitioner; an
    "Answer" is almost always filed by the defendant/respondent. Callers must
    treat this as a one-click suggestion, never pre-fill it: it's a heuristic
    that can be wrong (e.g. a co-plaintiff answering on their own claim), and
    silently pre-selecting a party's legal role is the kind of mistake a filer
    might not think to double check.
    """
    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    filing_type_name = (lead.filing_type_name if lead else "") or ""

    if "answer" in filing_type_name.lower():
        keywords = _RESPONDING_PARTY_KEYWORDS
    elif draft.existing_case == ExistingCase.NEW:
        keywords = _INITIATING_PARTY_KEYWORDS
    else:
        return None

    for party_type in party_types:
        name = party_type["name"].lower()
        if any(keyword in name for keyword in keywords):
            return party_type
    return None


def ensure_required_parties(draft: FilingDraft, party_types: list[dict[str, Any]]) -> None:
    parties = FilingParty.objects.filter(draft=draft)
    covered = set(parties.exclude(party_type="").values_list("party_type", flat=True))
    last_order = parties.filter(role="other").order_by("-sort_order").values_list("sort_order", flat=True).first()
    next_order = 0 if last_order is None else last_order + 1
    for party_type in party_types:
        code = party_type["code"]
        if not party_type["required"] or code in covered:
            continue
        FilingParty.objects.create(
            draft=draft,
            role="other",
            sort_order=next_order,
            party_type=code,
            party_type_name=party_type["name"],
        )
        covered.add(code)
        next_order += 1


def get_case_questions(draft: FilingDraft) -> list[dict[str, Any]]:
    case_type = draft.case_type_name or draft.case_type_code
    lowered = case_type.lower()
    if "dissolution" in lowered or "divorce" in lowered:
        case_type = "dissolution"
    config = config_loader.get_case_type_config(
        draft.jurisdiction,
        case_type,
        court=draft.court_code,
    )
    questions: list[dict[str, Any]] = []
    for section in (config or {}).get("sections", {}).values():
        for group in section.get("fields", []):
            for field in group.get("fields", []):
                name = field.get("name", "")
                if name not in {"has_children", "child_count"}:
                    continue
                questions.append(
                    {
                        "name": name,
                        "label": field.get("label") or name.replace("_", " ").title(),
                        "type": field.get("type", "text"),
                        "required": bool(field.get("required")),
                        "options": field.get("options", []),
                        "min": field.get("min"),
                        "max": field.get("max"),
                        "group": group.get("section_title", "Case details"),
                    }
                )
    return questions


def parse_question_answer(question: dict[str, Any], value: Any) -> Any:
    if question["type"] == "radio":
        if str(value).lower() == "true":
            return True
        if str(value).lower() == "false":
            return False
    if question["type"] == "number" and value not in (None, ""):
        return int(value)
    return str(value or "").strip()
