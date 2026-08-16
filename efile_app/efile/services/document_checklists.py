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


def _applies_to_lead(item: dict[str, Any], lead_filing_type_name: str) -> bool:
    """Check an item's optional filing-type condition against the lead document."""

    condition = item.get("when") or {}
    if not isinstance(condition, dict):
        return True
    wanted = condition.get("lead_filing_type_names")
    if not wanted:
        return True
    if isinstance(wanted, str):
        wanted = [wanted]
    return normalize_name(lead_filing_type_name) in {normalize_name(value) for value in wanted}


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


def _checklist_items(entry: dict[str, Any], lead_filing_type_name: str) -> dict[str, dict[str, Any]]:
    documents = entry.get("documents") or {}
    if not isinstance(documents, dict):
        logger.warning("Checklist config has a non-dictionary documents block; ignoring it")
        return {}

    items: list[tuple[str, dict[str, Any]]] = []
    for item_id, raw in documents.items():
        if not isinstance(raw, dict):
            logger.warning("Checklist item %r is not a mapping; ignoring it", item_id)
            continue
        # A court override removes an inherited item with "include: false".
        if raw.get("include") is False:
            continue
        if not _applies_to_lead(raw, lead_filing_type_name):
            continue

        item: dict[str, Any] = {
            "label": str(raw.get("label") or item_id.replace("_", " ").capitalize()),
            "requirement": _requirement(raw, item_id),
        }
        if raw.get("description"):
            item["description"] = str(raw["description"])
        if raw.get("role"):
            item["role"] = str(raw["role"])
        items.append((item_id, item))

    # Strongest guidance first, configuration order within a level.
    items.sort(key=lambda pair: REQUIREMENT_ORDER.index(pair[1]["requirement"]))
    return dict(items)


def resolve_document_checklist(
    jurisdiction: str,
    court_code: str = "",
    case_category_name: str = "",
    case_type_name: str = "",
    lead_filing_type_name: str = "",
) -> dict[str, dict[str, Any]]:
    """Return the configured checklist for one filing, or an empty dict.

    A checklist configured for the case type wins. If no case type matches, broad
    case category guidance is used instead. The two are never merged: a specific
    list replaces a general one.

    The result holds semantic data only -- our own item IDs, labels, requirement
    levels, and optional descriptions. No court codes leak into it.
    """

    if not jurisdiction:
        return {}

    sections = config_loader.get_document_checklist_config(jurisdiction, court=court_code or None)

    for section_name, name in (("case_types", case_type_name), ("case_categories", case_category_name)):
        match = _find_match(sections.get(section_name) or {}, name)
        if match is None:
            continue
        key, entry = match
        if not entry.get("documents"):
            continue
        logger.debug("Document checklist for %r resolved to %s.%s", name, section_name, key)
        return _checklist_items(entry, lead_filing_type_name)

    return {}
