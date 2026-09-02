from __future__ import annotations

import logging
import re
from typing import Any

import requests
from django.conf import settings

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.party_sides import PARTY_SIDE_KEYWORDS, PartySide, side_for_party_type_name
from efile.services.document_checklists import party_type_keywords_for_role
from efile.services.extracted_parties import extracted_party_suggestions, party_display_name
from efile.services.party_requirements import address_is_blank, address_is_complete, party_address_requirement
from efile.utils.config_loader import config_loader
from efile.workflow import ExistingCase

logger = logging.getLogger(__name__)

# Keywords matched against a court's own party-type names (e.g.
# "Plaintiff/Petitioner") to turn a case-posture guess into one of that
# court's actual codes. The same lists decide which code a party's side maps
# onto, so they live with the sides themselves.
_INITIATING_PARTY_KEYWORDS = PARTY_SIDE_KEYWORDS[PartySide.INITIATING]
_RESPONDING_PARTY_KEYWORDS = PARTY_SIDE_KEYWORDS[PartySide.RESPONDING]

# What the parties screen posts when the person filing says they are not one
# of the parties themselves. It can never collide with a court's own code:
# every value is checked against the court's published list before it is
# stored, and this one is deliberately not in any of them.
NOT_A_PARTY = "__not_a_party__"


def party_is_complete(party: FilingParty, *, draft=None, party_types=None) -> bool:
    has_name = bool(party.organization_name or (party.first_name and party.last_name))
    if getattr(party, "role", "") == "filer" and not party.party_type:
        # Someone filing for a party they are not. They have no party type to
        # be missing, and no caption address to complete: their name and
        # address were collected on their own screen and reach the court as
        # the filing's contact rather than as a person in the case.
        return has_name
    address_required = party_address_requirement(
        draft or getattr(party, "draft", None),
        party,
        party_types=party_types,
    ).required
    valid_address = address_is_complete(party) or (not address_required and address_is_blank(party))
    return bool(party.party_type and has_name and valid_address)


def incomplete_parties(draft: FilingDraft, *, party_types=None):
    return [
        party
        for party in FilingParty.objects.filter(draft=draft)
        if not party_is_complete(party, draft=draft, party_types=party_types)
    ]


def filer_is_party(draft: FilingDraft) -> bool:
    """True when the person signed in is one of the parties in the case.

    Being the filer and being a party are two different things. Most people
    using this are self-represented and are both, but a parent filing for a
    child, or a neighbour helping someone answer an eviction, is neither
    named in the caption nor required to be.
    """

    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    return bool(filer and filer.party_type)


def filing_parties(draft: FilingDraft) -> list[FilingParty]:
    """The parties this filing is made on behalf of.

    Tyler needs at least one and names it on every document in the envelope
    (``filing_parties`` in a court bundle). It is the filer's own row when
    they are a party, and whoever they named when they are not.

    Falls back to the filer when nothing has been marked: a draft that was
    answered before this question existed said only that the filer was a
    party, and back then that was the same answer.
    """

    marked = list(FilingParty.objects.filter(draft=draft, is_filing_party=True))
    if marked:
        return marked
    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    return [filer] if filer is not None and filer.party_type else []


def set_filing_parties(draft: FilingDraft, parties) -> None:
    """Record who this filing is on behalf of, and no one else.

    Written as a replacement rather than a toggle: a filer who corrects
    "I am the plaintiff" to "I am filing for my daughter" must not leave
    themselves behind as a second filing party.
    """

    wanted = {party.pk for party in parties}
    for party in FilingParty.objects.filter(draft=draft):
        if party.is_filing_party != (party.pk in wanted):
            party.is_filing_party = party.pk in wanted
            party.save(update_fields=["is_filing_party", "updated_at"])


def self_claimed_party(draft: FilingDraft) -> FilingParty | None:
    """The party the filer ticked as themselves while reviewing the document."""

    if filer_is_party(draft):
        return None
    return FilingParty.objects.filter(draft=draft, role="other", is_self=True).first()


def case_has_named_parties(draft: FilingDraft) -> bool:
    """Whether the case's other people have been settled already.

    Once they have, a suggestion about which side the filer is probably on is
    not a help but a contradiction: it is guessing at something the filer has
    already been asked and answered. True however they were settled -- read
    off the document, or typed in by hand.
    """

    return any(party_display_name(party) for party in FilingParty.objects.filter(draft=draft, role="other"))


def document_named_the_parties(draft: FilingDraft) -> bool:
    """Whether the people in this case came off the document or out of a form.

    A filer who turned AI off gets a keyword scan, which reads a form number
    and a case number and never a name (see
    ``document_extractions.keyword_document_analysis``), so on that route the
    party list is entirely their own typing. Screens that would otherwise
    credit a reading have to know the difference, or they tell the filer the
    system did something for them that it did not do.
    """

    return bool(extracted_party_suggestions(draft.extracted_guesses))


def filer_name_match(draft: FilingDraft) -> FilingParty | None:
    """The caption party who has the filer's own name, when they are not one.

    A document names the person filing along with everyone else, so this is
    the strongest signal there is that they belong in the case -- stronger
    than the case-posture guess, because the document itself said which side
    they were on. It is a suggestion and not an answer: two people share a
    name often enough, and a parent filing for a child they are named after
    is exactly the case this whole screen exists for. The parties screen puts
    it to them; :func:`claim_party_as_filer` is what confirming it does.
    """

    if filer_is_party(draft):
        return None
    matches = _filer_duplicates(draft)
    return matches[0] if matches else None


def names_match(filer: FilingParty | None, party: FilingParty | None) -> bool:
    """Whether two rows are the same name once spelling is set aside."""

    if filer is None or party is None:
        return False
    filer_name = _comparable(party_display_name(filer))
    return bool(filer_name) and filer_name == _comparable(party_display_name(party))


def claim_replaces_a_name(filer: FilingParty | None, party: FilingParty | None) -> bool:
    """Whether claiming this party would put a different name in the case.

    Claiming the blank row someone started is not replacing anybody, and
    claiming a row that already carries the filer's name is confirming who
    they are. Only the third case -- a named party who is not them by name --
    changes what the court is told the case is about, and only that one has a
    question to ask first.
    """

    if party is None:
        return False
    return bool(party_display_name(party)) and not names_match(filer, party)


def claim_party_as_filer(draft: FilingDraft, party: FilingParty, *, use_party_name: bool = False) -> None:
    """Answer "that party is me": become them, and stop listing them twice.

    The filer's own row is the one kept, because it is the one with the
    address and email the court needs; the claimed row is deleted rather than
    left behind as a second person in the case.

    Which name the court then sees is a real question whenever the two rows
    are not the same name, and it is the caller's to have asked. Passing
    ``use_party_name`` keeps what the case already says -- the right answer
    for a filer whose caption name is not the one on their account -- and
    the default keeps their own.
    """

    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    if filer is None:
        return
    name_fields: list[str] = []
    if use_party_name and party_display_name(party):
        filer.first_name = party.first_name
        filer.middle_name = party.middle_name
        filer.last_name = party.last_name
        filer.suffix = party.suffix
        filer.organization_name = party.organization_name
        name_fields = ["first_name", "middle_name", "last_name", "suffix", "organization_name"]
    filer.party_type = party.party_type or filer.party_type
    filer.party_type_name = party.party_type_name or filer.party_type_name
    filer.party_side = filer.party_side or party.party_side
    filer.party_role_hint = filer.party_role_hint or party.party_role_hint
    # A row claimed before anyone gave it a court role leaves the role question
    # unanswered rather than making the filer a filing party with no role at
    # all, which is a state the payload cannot say anything useful about.
    filer.is_filing_party = bool(filer.party_type)
    filer.save(
        update_fields=[
            *name_fields,
            "party_type",
            "party_type_name",
            "party_side",
            "party_role_hint",
            "is_filing_party",
            "updated_at",
        ]
    )
    party.delete()
    if filer.is_filing_party:
        set_filing_parties(draft, [filer])


def discard_empty_parties(draft: FilingDraft) -> int:
    """Delete party rows that were started and never filled in.

    Adding a person creates the row before the form that names them, so
    leaving that form without saving strands a row with nothing in it. It
    reaches the party list as a nameless entry the filer did not add on
    purpose and cannot tell apart from one they did.

    A nameless row that carries a party type is left alone: that is the
    court's own required-party placeholder, which is waiting for a name
    rather than missing one by accident.
    """

    empty = [
        party
        for party in FilingParty.objects.filter(draft=draft, role="other", party_type="")
        if not party_display_name(party) and not party.party_side
    ]
    for party in empty:
        party.delete()
    return len(empty)


def filing_party_candidates(draft: FilingDraft) -> list[FilingParty]:
    """The parties a filer who is not one could say they are filing for.

    Only parties that have been named: a blank row the court's required-party
    rule created is not yet anybody, and choosing it would tell the court
    this filing is on behalf of no one.
    """

    return [
        party
        for party in FilingParty.objects.filter(draft=draft, role="other").order_by("sort_order", "created_at")
        if party_display_name(party)
    ]


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
            # Tyler does not currently return one of these fields in the
            # Illinois staging lists we checked. Preserve support for the live
            # metadata rather than forcing a future flag into static YAML.
            "address_required": any(
                str(item.get(key, "")).lower() == "true"
                for key in ("addressrequired", "addressRequired", "partyaddressrequired", "requirespartyaddress")
            ),
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

    Being the one filed for moves across with it. Someone who said they were
    filing for a party who turns out to be themselves under a second name is
    still filing for that party, and dropping the flag with the row would
    leave the envelope on behalf of nobody.

    Only ever folds into a filer who has said they are a party. Before that,
    a caption name matching theirs is a question rather than an answer --
    they may be that party, or they may be a different person with the same
    name, or they may be filing for a relative they share a name with. It is
    put to them on the parties screen instead; see :func:`filer_name_match`.
    """

    if not filer_is_party(draft):
        return side_named_for_filer(draft)

    duplicates = _filer_duplicates(draft)
    if not duplicates:
        return side_named_for_filer(draft)

    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    side = filer.party_side if filer is not None else ""
    files_on_behalf = filer.is_filing_party if filer is not None else False
    for party in duplicates:
        side = side or party.party_side or side_for_party_type_name(party.party_type_name)
        files_on_behalf = files_on_behalf or party.is_filing_party
        party.delete()
    if filer is None:
        return side
    updated = []
    if side and not filer.party_side:
        filer.party_side = side
        updated.append("party_side")
    if files_on_behalf and not filer.is_filing_party:
        filer.is_filing_party = True
        updated.append("is_filing_party")
    if updated:
        filer.save(update_fields=[*updated, "updated_at"])
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
