from __future__ import annotations

import logging
import re
from typing import Any

import requests
from django.conf import settings

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.party_sides import PARTY_SIDE_KEYWORDS, PartySide, side_for_party_type_name
from efile.services.document_checklists import party_type_keywords_for_role
from efile.services.extracted_parties import party_display_name
from efile.utils.config_loader import config_loader
from efile.workflow import ExistingCase

logger = logging.getLogger(__name__)

# Keywords matched against a court's own party-type names (e.g.
# "Plaintiff/Petitioner") to turn a case-posture guess into one of that
# court's actual codes. The same lists decide which code a party's side maps
# onto, so they live with the sides themselves.
_INITIATING_PARTY_KEYWORDS = PARTY_SIDE_KEYWORDS[PartySide.INITIATING]
_RESPONDING_PARTY_KEYWORDS = PARTY_SIDE_KEYWORDS[PartySide.RESPONDING]


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
    """Suggest the filer's role -- a suggestion, never authoritative.

    When the case type has sides and the filer has already said which one is
    theirs, that answer decides the suggestion. Otherwise it falls back to case
    posture: a brand new case is almost always opened by the
    plaintiff/petitioner; an "Answer" is almost always filed by the
    defendant/respondent. Callers must treat the result as a one-click
    suggestion, never pre-fill it: it can be wrong (e.g. a co-plaintiff
    answering on their own claim), and silently pre-selecting a party's legal
    role is the kind of mistake a filer might not think to double check.
    """
    # The document itself is the best answer there is: if it named the filer,
    # it also said which side of the caption they were on.
    named_side = side_named_for_filer(draft)
    if named_side:
        match = match_party_type(party_types, PARTY_SIDE_KEYWORDS.get(named_side, ()))
        if match is not None:
            return match

    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    filing_type_name = (lead.filing_type_name if lead else "") or ""

    keywords = party_type_keywords_for_role(
        jurisdiction=draft.jurisdiction,
        court_code=draft.court_code,
        case_category_name=draft.case_category_name,
        case_type_name=draft.case_type_name,
        filer_role=draft.filer_role,
    )
    if not keywords:
        if "answer" in filing_type_name.lower():
            keywords = _RESPONDING_PARTY_KEYWORDS
        elif draft.existing_case == ExistingCase.NEW:
            keywords = _INITIATING_PARTY_KEYWORDS
        else:
            return None

    return match_party_type(party_types, keywords)


_WORDS = re.compile(r"[a-z]+")
# Courts list alternatives with a slash ("Plaintiff/Petitioner"), so each side
# of one is its own name. A hyphen is the opposite: "Cross-Defendant" is one
# name for a party that is not simply the defendant.
_NAME_ALTERNATIVES = re.compile(r"[\s/,;]+")


def _party_type_names(name: str) -> set[str]:
    return {word.strip("().") for word in _NAME_ALTERNATIVES.split(name.lower()) if word.strip("().")}


def match_party_type(party_types: list[dict[str, Any]], keywords) -> dict[str, Any] | None:
    """Pick the court party type a set of keywords names, or None.

    A court that offers both "Defendant" and "Cross-Defendant" must give a
    caption's plain defendant the plain one, so a party type that *is* the
    keyword is taken ahead of one that merely contains it.
    """

    keywords = {keyword.lower() for keyword in keywords or ()}
    if not keywords:
        return None
    for party_type in party_types:
        if _party_type_names(party_type["name"]) & keywords:
            return party_type
    for party_type in party_types:
        name = party_type["name"].lower()
        if any(keyword in name for keyword in keywords):
            return party_type
    return None


def party_type_for_party(party: FilingParty, party_types: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The court party type this party's side means, for this case type.

    The role the document printed is tried first: a court that publishes a
    "Guardian Ad Litem" type should get the guardian, not whatever generic
    type their side would otherwise fall back to.
    """

    hint = match_party_type(party_types, _WORDS.findall(party.party_role_hint.lower()))
    if hint is not None:
        return hint
    return match_party_type(party_types, PARTY_SIDE_KEYWORDS.get(party.party_side, ()))


def apply_party_sides(draft: FilingDraft, party_types: list[dict[str, Any]]) -> None:
    """Give every side-tagged party the court's own code for that side.

    This is the second half of the split described in ``efile.party_sides``:
    the document said which side each person is on, and the case type -- known
    only now -- says what that side is called here. A party the filer has
    already given a type keeps it; nothing resolved is ever overwritten.
    """

    if not party_types:
        return
    for party in FilingParty.objects.filter(draft=draft, role="other", party_type=""):
        if not party.party_side:
            continue
        match = party_type_for_party(party, party_types)
        if match is None:
            continue
        party.party_type = match["code"]
        party.party_type_name = match["name"]
        party.save(update_fields=["party_type", "party_type_name", "updated_at"])


def _comparable(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _filer_duplicates(draft: FilingDraft) -> list[FilingParty]:
    """The other-party rows that are the filer under a second name.

    A document names the filer along with everyone else, so the roster read
    off it and the filer's own row are routinely the same person twice.
    """

    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    filer_name = _comparable(party_display_name(filer)) if filer else ""
    if not filer_name:
        return []
    return [
        party
        for party in FilingParty.objects.filter(draft=draft, role="other")
        if _comparable(party_display_name(party)) == filer_name
    ]


def side_named_for_filer(draft: FilingDraft) -> str:
    """The side the document put the filer on, when it named them at all."""

    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    if filer is not None and filer.party_side:
        return filer.party_side
    for party in _filer_duplicates(draft):
        side = party.party_side or side_for_party_type_name(party.party_type_name)
        if side:
            return side
    return ""


def absorb_filer_duplicates(draft: FilingDraft) -> str:
    """Fold the party rows the filer already is into the filer, and report the side.

    The filer's own row is the one carrying their address and contact
    details, so that is the one that survives; the duplicate would otherwise
    reach the court as a second, address-less person of the same name. The
    side moves across first, so deleting the duplicate does not throw away
    the document's own answer to the question the filer is being asked.
    """

    duplicates = _filer_duplicates(draft)
    if not duplicates:
        return side_named_for_filer(draft)

    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    side = filer.party_side if filer is not None else ""
    for party in duplicates:
        side = side or party.party_side or side_for_party_type_name(party.party_type_name)
        party.delete()
    if filer is not None and side and not filer.party_side:
        filer.party_side = side
        filer.save(update_fields=["party_side", "updated_at"])
    return side


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


def needs_amount_in_controversy(draft: FilingDraft) -> bool:
    """True if any organized document's filing type requires a dollar amount.

    Tyler flags this per filing type (FilingCode.amountincontroversy ==
    "Required"), recorded onto FilingDocument when the filer picks it in
    organize_documents. The EFSP rejects the whole filing without it.
    """
    return FilingDocument.objects.filter(draft=draft, filing_requires_amount_in_controversy=True).exists()


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
