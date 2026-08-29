#!/usr/bin/env python3
"""Apply conservative, repeatable cleanup to the form-to-taxonomy crosswalk."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from audit_form_code_crosswalk import (
    DEFAULT_CROSSWALK,
    expected_summary,
    normalized_name,
)

SCHEMA_VERSION = "1.2.0"
CHANGE_DATE = "2026-08-27"
CANONICAL_FORMS_ROOT = DEFAULT_CROSSWALK.parent / "canonical_forms"
SEED_MANIFEST = DEFAULT_CROSSWALK.parents[2] / "synthetic" / "seed_manifest.jsonl"

# These documents were caught by a title-only non-form heuristic even though
# the title describes a form, or the PDF combines instructions with a form.
FORM_FLAG_CORRECTIONS = {
    "VT-400-00800",  # Information Sheet
    "VT-700-00209A-0",  # Information Sheet for Non-Resident Ministers
    "VT-100-00257",  # Instructions and Small Claims Complaint in one PDF
    "VT-400-00817A",  # Supplemental Information Sheet
    "IL-AOIC-063",  # Certification for Exemption from E-Filing
    "IL-AOIC-064",
    "IL-AOIC-065",
}

# The current test-site route keys are retained only to document where a label
# was observed. Stable court names are the lookup keys across environments.
COURT_NAMES_BY_OBSERVED_ROUTE_KEY = {
    "massachusetts": {
        "1176": "Middlesex Superior Court",
        "352": "Essex Probate and Family Court",
        "418": "BMC - Brighton",
        "537": "Housing - Eastern (Boston)",
        "appeals:acp": "Appeals Court - Panel (P docket)",
    },
    "vermont": {
        "sc:addison": "Addison Unit",
        "sc:chittendon": "Chittenden Unit",
        "sc:rutland": "Rutland Unit",
        "sc:washington": "Washington Unit",
    },
    "illinois": {
        "TAC1": "Appellate Court – 1st District",
        "TSUPCRT": "Supreme Court of Illinois",
        "cook:chd1": "Cook County - Chancery - District 1 - Chicago",
        "cook:cvd1": "Cook County - Municipal Civil - District 1 - Chicago",
        "cook:dr1": "Cook County - Domestic Relations - District 1 - Chicago",
        "cook:pr1": "Cook County - Probate - District 1 - Chicago",
        "dupage": "DuPage County",
    },
}


def unique_strings(values: list[Any]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def normalized_form_id(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def source_url_overlays() -> dict[tuple[str, str], list[str]]:
    overlays: dict[tuple[str, str], list[str]] = {}
    if not SEED_MANIFEST.exists():
        return overlays
    for line in SEED_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        key = (item["jurisdiction"], normalized_form_id(item.get("form_number")))
        overlays.setdefault(key, []).append(item["source_url"])
    return overlays


def document_role(form: dict[str, Any]) -> str:
    if form.get("is_form") is True:
        return "court_form"
    title = str(form.get("canonical_name") or "").casefold()
    if "brochure" in title:
        return "brochure"
    if "guide" in title or "guidelines" in title:
        return "guide"
    if (
        "instructions" in title
        or title.startswith("how to")
        or "getting started" in title
    ):
        return "instructions"
    return "reference"


def normalize_form(
    form: dict[str, Any],
    source_overlays: dict[tuple[str, str], list[str]] | None = None,
) -> None:
    canonical_id = form.get("canonical_id")
    title = str(form.get("canonical_name") or "").casefold()
    if canonical_id in FORM_FLAG_CORRECTIONS:
        form["is_form"] = True
    elif (
        title.startswith("checklist")
        or title.startswith("getting started")
        or title.startswith("filing for ")
    ):
        form["is_form"] = False

    source_values = list(form.pop("source_urls", []) or [])
    legacy_source = form.pop("source_url", None)
    if legacy_source:
        source_values.append(legacy_source)
    if source_overlays:
        source_values.extend(
            source_overlays.get(
                (form.get("jurisdiction"), normalized_form_id(form.get("form_id"))), []
            )
        )
    if form.get("jurisdiction") == "illinois":
        source_values = [
            urljoin("https://www.illinoiscourts.gov", str(value))
            for value in source_values
        ]
    form["source_urls"] = unique_strings(source_values)
    form.setdefault("revision", None)
    form["document_role"] = document_role(form)

    # is_efileable describes this exact document, not the surrounding form
    # suite. Instructions, guides, and brochures are not filing documents.
    if form.get("is_form") is False:
        form["is_efileable"] = False


def normalize_mapping(mapping: dict[str, Any], form: dict[str, Any]) -> None:
    old_status = mapping.pop("review_status", None)
    old_reviewed_at = mapping.pop("reviewed_at", None)
    existing_catalog_status = mapping.get("catalog_status")
    existing_catalog_checked_at = mapping.get("catalog_checked_at")
    verification = mapping.setdefault(
        "human_verification",
        {"verified": False, "verified_by": None, "verified_at": None, "notes": None},
    )

    for level in ("category", "case_type", "filing_type"):
        if isinstance(mapping.get(level), str):
            mapping[level] = mapping[level].strip()
    fees = mapping.pop("fees", []) or []
    legacy_fee = mapping.pop("fee", None)
    if legacy_fee is not None:
        fees.append(legacy_fee)
    mapping["fees"] = unique_strings(fees)

    if form.get("is_form") is False:
        association_status = "not_applicable"
    elif form.get("is_efileable") is False:
        association_status = "not_efileable"
    elif verification.get("verified") is True:
        association_status = "human_verified"
    else:
        association_status = "unverified_suggestion"

    has_observation = (
        bool(mapping.get("filing_type"))
        and "staging observation:" in str(mapping.get("notes") or "").casefold()
    )
    durable_catalog_statuses = {
        "current",
        "partially_current",
        "partial_observation",
        "not_current",
        "not_checked",
    }
    if association_status in {"not_applicable", "not_efileable"}:
        catalog_status = "not_applicable"
    elif existing_catalog_status in durable_catalog_statuses:
        catalog_status = existing_catalog_status
    elif (
        has_observation
        or old_status == "verified_live"
        or existing_catalog_status == "observed_live"
    ):
        catalog_status = (
            "observed_live"
            if all(
                mapping.get(level) for level in ("category", "case_type", "filing_type")
            )
            else "partial_observation"
        )
    else:
        catalog_status = "not_checked"

    mapping["catalog_status"] = catalog_status
    mapping["catalog_checked_at"] = (
        old_reviewed_at or existing_catalog_checked_at
        if catalog_status not in {"not_checked", "not_applicable"}
        else None
    )
    mapping["association_status"] = association_status
    if catalog_status == "not_applicable":
        mapping.pop("catalog_validation", None)

    scope = mapping.setdefault("court_scope", {})
    legacy_route_keys = scope.pop("court_codes", [])
    old_route_keys = [
        str(value)
        for value in (legacy_route_keys or scope.get("observed_route_keys", []))
        if str(value) != "none"
    ]
    jurisdiction = form["jurisdiction"]
    court_index = COURT_NAMES_BY_OBSERVED_ROUTE_KEY[jurisdiction]
    scope["court_names"] = [court_index[key] for key in old_route_keys]
    scope["observed_route_keys"] = old_route_keys


def stable_mapping_key(mapping: dict[str, Any]) -> tuple[Any, ...]:
    scope = mapping.get("court_scope", {})
    return (
        tuple(normalized_name(value) for value in scope.get("court_names", [])),
        mapping.get("filing_phase"),
        *(
            normalized_name(mapping.get(level))
            for level in ("category", "case_type", "filing_type")
        ),
    )


def merge_duplicate_mappings(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for mapping in mappings:
        key = stable_mapping_key(mapping)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = mapping
            merged.append(mapping)
            continue
        existing["confidence"] = max(
            existing.get("confidence", 0), mapping.get("confidence", 0)
        )
        existing["fees"] = unique_strings(
            [*existing.get("fees", []), *mapping.get("fees", [])]
        )
        existing["discriminators"] = unique_strings(
            [*existing.get("discriminators", []), *mapping.get("discriminators", [])]
        )
        existing["notes"] = (
            " | ".join(unique_strings([existing.get("notes"), mapping.get("notes")]))
            or None
        )
        if mapping.get("catalog_status") == "observed_live":
            existing["catalog_status"] = "observed_live"
            existing["catalog_checked_at"] = max(
                filter(
                    None,
                    [
                        existing.get("catalog_checked_at"),
                        mapping.get("catalog_checked_at"),
                    ],
                ),
                default=None,
            )
        if mapping.get("association_status") == "human_verified":
            existing["association_status"] = "human_verified"
            existing["human_verification"] = mapping["human_verification"]
    return merged


def normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    overlays = source_url_overlays()
    for entry in document["registry"]:
        form = entry["form"]
        normalize_form(form, overlays)
        for mapping in entry.get("mappings", []):
            normalize_mapping(mapping, form)
        entry["mappings"] = merge_duplicate_mappings(entry.get("mappings", []))

    document["schema_version"] = SCHEMA_VERSION
    document["updated_at"] = CHANGE_DATE
    document["description"] = (
        "Canonical court form registry with candidate mappings to Tyler ECF taxonomy names. "
        "Category, case-type, filing-type, and court names are the durable cross-environment identifiers. "
        "Numeric taxonomy keys and court route keys are staging observations only and must be resolved "
        "again by name in the selected environment."
    )
    document["mapping_status_schema"] = {
        "catalog_status": {
            "observed_live": "Complete historical observation awaiting the current name-based hierarchy audit.",
            "current": "The complete named hierarchy is currently available in every court in scope.",
            "partially_current": "The named hierarchy is current in only some courts in scope.",
            "partial_observation": "A label was observed, but the complete hierarchy cannot be checked.",
            "not_current": "The recorded named hierarchy was absent at the latest check.",
            "not_checked": "The candidate has not been confirmed in the recorded catalog hierarchy.",
            "not_applicable": "The document is not an e-fileable court form.",
        },
        "association_status": {
            "unverified_suggestion": "Automated candidate; do not select deterministically.",
            "human_verified": "A reviewer confirmed the form-to-taxonomy association.",
            "not_efileable": "Court form, but not e-fileable.",
            "not_applicable": "Instructions, guide, brochure, or other non-form document.",
        },
        "confidence": (
            "Candidate-ranking score, not a calibrated correctness probability. Human verification and live "
            "catalog availability are recorded separately."
        ),
    }
    document["human_verification_schema"]["description"] = (
        "Human verification confirms the form-to-taxonomy association, not merely that a label appears in "
        "a Tyler catalog. Set verified=true, association_status=human_verified, verified_by, and verified_at."
    )
    change = {
        "version": SCHEMA_VERSION,
        "date": CHANGE_DATE,
        "changes": [
            "Added punctuation-insensitive printed-code aliases for the sampled Illinois statewide forms",
            "Added registry records for the sampled statewide Complaint or Petition, Petition for Divorce with Children, and Minor Guardianship forms",
            "Recorded the Illinois sample codes as form identity only; no unverified Tyler taxonomy mappings were added",
        ],
    }
    document["changelog"] = [
        change,
        *[
            item
            for item in document.get("changelog", [])
            if item.get("version") != SCHEMA_VERSION
        ],
    ]
    document["summary"] = expected_summary(document)
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if normalization would change the file",
    )
    parser.add_argument(
        "--skip-canonical-forms",
        action="store_true",
        help="Do not normalize the source form inventories alongside the crosswalk",
    )
    args = parser.parse_args()

    original = args.crosswalk.read_text(encoding="utf-8")
    document = json.loads(original)
    normalize_document(document)
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    canonical_changes: list[tuple[Path, str]] = []
    if not args.skip_canonical_forms:
        for canonical_path in sorted(CANONICAL_FORMS_ROOT.glob("*_forms.json")):
            canonical_original = canonical_path.read_text(encoding="utf-8")
            canonical_forms = json.loads(canonical_original)
            overlays = source_url_overlays()
            for form in canonical_forms:
                normalize_form(form, overlays)
            canonical_rendered = (
                json.dumps(canonical_forms, ensure_ascii=False, indent=2) + "\n"
            )
            if canonical_rendered != canonical_original:
                canonical_changes.append((canonical_path, canonical_rendered))
    if args.check:
        changed = [str(args.crosswalk)] if rendered != original else []
        changed.extend(str(path) for path, _ in canonical_changes)
        if changed:
            raise SystemExit("Not normalized: " + ", ".join(changed))
        print(f"{args.crosswalk} and canonical form inventories are normalized")
        return
    args.crosswalk.write_text(rendered, encoding="utf-8")
    for canonical_path, canonical_rendered in canonical_changes:
        canonical_path.write_text(canonical_rendered, encoding="utf-8")
    print(f"Normalized {args.crosswalk}")


if __name__ == "__main__":
    main()
