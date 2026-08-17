"""Resolve the partner-configured document checklist for a filing.

Partners describe, in the jurisdiction YAML, which documents a filer typically
needs for a kind of case. This module turns that configuration into a plain list
of guidance items.

Two rules shape the whole module:

* Configuration identifies a case category, case type, or filing type by the
  **name** the court's e-filing service returns, never by Tyler's numeric code.
  Those codes differ from court to court and change without notice; the names are
  stable, and a partner can read them. Codes are still fetched live and used for
  the actual filing -- they simply never appear in partner configuration.
* Matching is deterministic. Names are normalized (case, spacing, dashes) and
  then compared exactly. Nothing is guessed: when a court renames something, a
  partner adds the new name to ``matches.names`` and the checklist works again.

Requirement levels (``always``, ``usually``, ``sometimes``) are advice for the
filer. Nothing here blocks a submission.

A case type may also declare the sides a filing can come from -- ``filer_roles``
-- because in a two-sided case the same case type means two different jobs. The
landlord in an eviction files a complaint; the tenant files an appearance and an
answer, and needs the same fee waiver described in the opposite direction. Items
name the sides they belong to, and may reword themselves per side.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from efile.utils.config_loader import config_loader

logger = logging.getLogger(__name__)

# Strongest first. Also the display order of the checklist.
REQUIREMENT_ORDER: tuple[str, ...] = ("always", "usually", "sometimes")
DEFAULT_REQUIREMENT = "sometimes"

REQUIREMENT_LABELS: dict[str, str] = {
    "always": "Always needed",
    "usually": "Usually needed",
    "sometimes": "Sometimes needed",
}


def _is_web_link(url: str) -> bool:
    return url.lower().startswith(("https://", "http://"))


# What a per-side override may change about a shared item. Deliberately narrow:
# a side may be told about the same document in its own words, and may need it
# more or less often, but must not be handed a different document under an ID
# the other side uses for something else.
_ROLE_OVERRIDABLE = frozenset({"label", "description", "requirement"})

# The same idea for the narrative about a kind of filing: each side of a case
# gets its own explanation and its own place to read more.
_ABOUT_OVERRIDABLE = frozenset({"summary", "learn_more_url", "learn_more_label"})

# Courts write the same name with a hyphen, an en dash, or an em dash -- Cook
# County's own case type list uses two different dashes for the same pair of case
# types. Treat them as one character rather than asking partners to guess.
_DASHES = re.compile("[\u2010-\u2015\u2212]")
_WHITESPACE = re.compile(r"\s+")


def normalize_name(value: Any) -> str:
    """Fold a court-supplied name into its comparable form."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _DASHES.sub("-", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip().lower()


def _configured_names(entry: dict[str, Any]) -> list[str]:
    matches = entry.get("matches") or {}
    if not isinstance(matches, dict):
        return []
    names: list[str] = []
    for key in ("names", "aliases"):
        values = matches.get(key) or []
        if isinstance(values, str):
            values = [values]
        names.extend(str(value) for value in values)
    return names


def _find_match(entries: dict[str, Any], name: str) -> tuple[str, dict[str, Any]] | None:
    """Find the single configured entry whose names include ``name``."""

    wanted = normalize_name(name)
    if not wanted:
        return None

    matched = [
        (key, entry)
        for key, entry in entries.items()
        if isinstance(entry, dict) and wanted in {normalize_name(value) for value in _configured_names(entry)}
    ]
    if not matched:
        return None
    if len(matched) > 1:
        # Two entries claiming one court name is a configuration mistake. Say so
        # loudly and stay deterministic by keeping the first one in file order.
        logger.warning(
            "Document checklist config matches %r more than once: %s",
            name,
            ", ".join(key for key, _entry in matched),
        )
    return matched[0]


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _matches_lead_filing_type(condition: Any, lead_filing_type_name: str) -> bool:
    """Test a ``lead_filing_type_names`` condition, which an empty list passes."""

    if not isinstance(condition, dict):
        return True
    wanted = _as_list(condition.get("lead_filing_type_names"))
    if not wanted:
        return True
    return normalize_name(lead_filing_type_name) in {normalize_name(value) for value in wanted}


def _applies_to_lead(item: dict[str, Any], lead_filing_type_name: str) -> bool:
    """Check an item's optional filing-type condition against the lead document."""

    return _matches_lead_filing_type(item.get("when") or {}, lead_filing_type_name)


def _applies_to_role(item: dict[str, Any], filer_role: str) -> bool:
    """Check an item's optional side-of-the-case condition.

    An item that names no side belongs to everyone. An item that names one is
    hidden from the other side entirely -- a tenant should not be told they
    might need to file an eviction complaint.
    """

    wanted = _as_list(item.get("for_roles"))
    if not wanted:
        return True
    return filer_role in wanted


def _worded_for_role(
    item: dict[str, Any],
    filer_role: str,
    allowed: frozenset[str] = _ROLE_OVERRIDABLE,
) -> dict[str, Any]:
    """Apply the wording this side of the case gets for a shared entry.

    "Proof that the other side got a copy" is one requirement, but it is not one
    sentence: the landlord served the tenant, and the tenant served the
    landlord. Only the keys in ``allowed`` may differ -- for an item that means
    wording and requirement level, so an override cannot turn an item into a
    different document.
    """

    by_role = item.get("by_role")
    if not isinstance(by_role, dict) or not filer_role:
        return item
    override = by_role.get(filer_role)
    if not isinstance(override, dict):
        return item
    return {**item, **{key: value for key, value in override.items() if key in allowed}}


def _requirement(item: dict[str, Any], item_id: str) -> str:
    requirement = normalize_name(item.get("requirement") or DEFAULT_REQUIREMENT)
    if requirement not in REQUIREMENT_ORDER:
        logger.warning(
            "Checklist item %r has unknown requirement %r; treating it as %r",
            item_id,
            item.get("requirement"),
            DEFAULT_REQUIREMENT,
        )
        return DEFAULT_REQUIREMENT
    return requirement


def _checklist_items(
    entry: dict[str, Any],
    lead_filing_type_name: str,
    filer_role: str = "",
) -> dict[str, dict[str, Any]]:
    documents = entry.get("documents") or {}
    if not isinstance(documents, dict):
        logger.warning("Checklist config has a non-dictionary documents block; ignoring it")
        return {}

    items: list[tuple[str, dict[str, Any]]] = []
    for item_id, configured in documents.items():
        if not isinstance(configured, dict):
            logger.warning("Checklist item %r is not a mapping; ignoring it", item_id)
            continue
        # A court override removes an inherited item with "include: false".
        if configured.get("include") is False:
            continue
        if not _applies_to_lead(configured, lead_filing_type_name):
            continue
        if not _applies_to_role(configured, filer_role):
            continue
        raw = _worded_for_role(configured, filer_role)

        item: dict[str, Any] = {
            "label": str(raw.get("label") or item_id.replace("_", " ").capitalize()),
            "requirement": _requirement(raw, item_id),
        }
        if raw.get("description"):
            item["description"] = str(raw["description"])
        if raw.get("role"):
            item["role"] = str(raw["role"])
        # What the court calls this document when it is filed, most preferred
        # first. Courts publish very different filing-type lists, so a partner
        # names every plausible one and the first the court actually offers is
        # the one used.
        filing_type_names = _as_list(raw.get("filing_type_names"))
        if filing_type_names:
            item["filing_type_names"] = filing_type_names
        items.append((item_id, item))

    # Strongest guidance first, configuration order within a level.
    items.sort(key=lambda pair: REQUIREMENT_ORDER.index(pair[1]["requirement"]))
    return dict(items)


def _resolve_entry(
    jurisdiction: str,
    court_code: str,
    case_category_name: str,
    case_type_name: str,
) -> dict[str, Any] | None:
    """Find the one configured entry that covers this case, or nothing.

    A checklist configured for the case type wins. If no case type matches, broad
    case category guidance is used instead. The two are never merged: a specific
    list replaces a general one.
    """

    if not jurisdiction:
        return None

    sections = config_loader.get_document_checklist_config(jurisdiction, court=court_code or None)

    for section_name, name in (("case_types", case_type_name), ("case_categories", case_category_name)):
        match = _find_match(sections.get(section_name) or {}, name)
        if match is None:
            continue
        key, entry = match
        if not entry.get("documents"):
            continue
        logger.debug("Document checklist for %r resolved to %s.%s", name, section_name, key)
        return entry

    return None


def resolve_filer_roles(
    jurisdiction: str,
    court_code: str = "",
    case_category_name: str = "",
    case_type_name: str = "",
    lead_filing_type_name: str = "",
) -> list[dict[str, Any]]:
    """Return the sides a filing in this case can come from, in config order.

    Empty for the great majority of case types, where everyone filing is doing
    the same job and asking which side they are on would be noise. Each side
    carries a ``suggested`` flag when the lead document is one only that side
    files -- a hint for the filer to confirm, never an answer on their behalf.
    """

    entry = _resolve_entry(jurisdiction, court_code, case_category_name, case_type_name)
    roles = (entry or {}).get("filer_roles")
    if not isinstance(roles, dict):
        return []

    resolved = []
    for role_id, role in roles.items():
        if not isinstance(role, dict):
            logger.warning("Filer role %r is not a mapping; ignoring it", role_id)
            continue
        condition = role.get("suggested_when")
        resolved.append(
            {
                "id": str(role_id),
                "label": str(role.get("label") or role_id.replace("_", " ").capitalize()),
                "description": str(role.get("description") or ""),
                "suggested": bool(condition) and _matches_lead_filing_type(condition, lead_filing_type_name),
            }
        )
    return resolved


def resolve_plan_guidance(
    jurisdiction: str,
    court_code: str = "",
    case_category_name: str = "",
    case_type_name: str = "",
    filer_role: str = "",
) -> dict[str, str]:
    """Return what a partner has written *about* this kind of filing.

    The checklist says what to bring; this says what the list is for, and what
    it cannot know. A filer reading a list of documents has a fair question --
    "is this everything?" -- and the honest answer needs more room than a
    caption, so it is a short narrative plus somewhere to read more.
    """

    entry = _resolve_entry(jurisdiction, court_code, case_category_name, case_type_name)
    about = (entry or {}).get("about")
    if not isinstance(about, dict):
        return {}
    about = _worded_for_role(about, filer_role, _ABOUT_OVERRIDABLE)
    guidance = {
        "summary": str(about.get("summary") or ""),
        "learn_more_url": str(about.get("learn_more_url") or ""),
        "learn_more_label": str(about.get("learn_more_label") or ""),
    }
    if guidance["learn_more_url"] and not _is_web_link(guidance["learn_more_url"]):
        # A "learn more" link that runs script or opens a file is not a link to
        # a website, whatever the configuration meant by it.
        logger.warning("Ignoring checklist learn_more_url that is not a web address: %r", guidance["learn_more_url"])
        guidance["learn_more_url"] = ""
    return {key: value for key, value in guidance.items() if value}


def party_type_keywords_for_role(
    jurisdiction: str,
    court_code: str = "",
    case_category_name: str = "",
    case_type_name: str = "",
    filer_role: str = "",
) -> list[str]:
    """Words that identify this side in a court's own party-type list."""

    if not filer_role:
        return []
    entry = _resolve_entry(jurisdiction, court_code, case_category_name, case_type_name)
    role = ((entry or {}).get("filer_roles") or {}).get(filer_role)
    if not isinstance(role, dict):
        return []
    return [normalize_name(keyword) for keyword in _as_list(role.get("party_type_keywords")) if keyword]


def resolve_document_checklist(
    jurisdiction: str,
    court_code: str = "",
    case_category_name: str = "",
    case_type_name: str = "",
    lead_filing_type_name: str = "",
    filer_role: str = "",
) -> dict[str, dict[str, Any]]:
    """Return the configured checklist for one filing, or an empty dict.

    When the case type distinguishes sides, the list is the one for
    ``filer_role``. Without a side, there is no honest list to show -- half the
    items would belong to the other party -- so nothing is returned until the
    filer says which side they are on.

    The result holds semantic data only -- our own item IDs, labels, requirement
    levels, and optional descriptions. No court codes leak into it.
    """

    entry = _resolve_entry(jurisdiction, court_code, case_category_name, case_type_name)
    if entry is None:
        return {}
    roles = entry.get("filer_roles")
    if isinstance(roles, dict) and roles and filer_role not in roles:
        return {}
    return _checklist_items(entry, lead_filing_type_name, filer_role)
