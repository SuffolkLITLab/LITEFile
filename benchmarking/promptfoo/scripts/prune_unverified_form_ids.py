#!/usr/bin/env python3
"""Remove registry records whose IDs lack a real downloaded-form match."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_form_code_crosswalk import DEFAULT_CROSSWALK, expected_summary

PROMPTFOO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = PROMPTFOO_ROOT.parents[1] / "court_forms" / "form_id_matches.json"
CANONICAL_FORMS_ROOT = DEFAULT_CROSSWALK.parent / "canonical_forms"
ALLOWED_STATUSES = {
    "unique_printed_id_match",
    "unique_printed_id_and_title_match",
    "printed_id_form_family",
}


def verified_canonical_ids(index_path: Path) -> set[str]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    forms = payload.get("forms", {}) if isinstance(payload, dict) else {}
    if not isinstance(forms, dict):
        raise ValueError("Form-ID index must contain a forms object")
    return {
        canonical_id
        for canonical_id, result in forms.items()
        if isinstance(result, dict) and result.get("status") in ALLOWED_STATUSES
    }


def is_title_identity(entry: dict) -> bool:
    """Keep curated no-ID forms whose title, rather than a code, is identity."""
    form = entry.get("form", {})
    return bool(
        isinstance(form, dict)
        and not str(form.get("form_id") or "").strip()
        and form.get("identity_basis")
        in {
            "unique_title",
            "unique_title_translation_family",
            "unique_downloaded_title",
            "downloaded_title_with_unverified_registry_id",
        }
    )


def prune_registry(document: dict, allowed_ids: set[str]) -> tuple[dict, list[str]]:
    registry = document.get("registry")
    if not isinstance(registry, list):
        raise ValueError("Crosswalk must contain a registry list")
    removed = [
        entry.get("form", {}).get("canonical_id", "")
        for entry in registry
        if entry.get("form", {}).get("canonical_id") not in allowed_ids
        and not is_title_identity(entry)
    ]
    document["registry"] = [
        entry
        for entry in registry
        if entry.get("form", {}).get("canonical_id") in allowed_ids
        or is_title_identity(entry)
    ]
    document["summary"] = expected_summary(document)
    changelog = document.setdefault("changelog", [])
    if not any(
        item.get("version") == "1.3.0" for item in changelog if isinstance(item, dict)
    ):
        changelog.insert(
            0,
            {
                "version": "1.3.0",
                "date": "2026-08-28",
                "changes": [
                    "Removed records without a positive exact printed-ID match in the downloaded court-form corpus.",
                    "Retained translated and revised PDFs as variants of one canonical form family when their printed ID and title corroborate the same filing form.",
                ],
            },
        )
    return document, removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    allowed_ids = verified_canonical_ids(args.index)
    document = json.loads(args.crosswalk.read_text(encoding="utf-8"))
    document, removed = prune_registry(document, allowed_ids)
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    canonical_updates = []
    for path in sorted(CANONICAL_FORMS_ROOT.glob("*_forms.json")):
        forms = json.loads(path.read_text(encoding="utf-8"))
        retained = [
            form
            for form in forms
            if form.get("canonical_id") in allowed_ids
            or (
                not str(form.get("form_id") or "").strip()
                and form.get("identity_basis")
                in {
                    "unique_title",
                    "unique_title_translation_family",
                    "unique_downloaded_title",
                    "downloaded_title_with_unverified_registry_id",
                }
            )
        ]
        canonical_updates.append(
            (path, json.dumps(retained, ensure_ascii=False, indent=2) + "\n")
        )

    if args.check:
        if rendered != args.crosswalk.read_text(encoding="utf-8"):
            raise SystemExit(
                f"Unpruned form IDs remain in {args.crosswalk}: {len(removed)} records"
            )
        print("Printed-ID pruning is current")
        return

    args.crosswalk.write_text(rendered, encoding="utf-8")
    for path, content in canonical_updates:
        path.write_text(content, encoding="utf-8")
    title_identities = sum(is_title_identity(entry) for entry in document["registry"])
    print(
        f"Retained {len(allowed_ids)} printed-ID-backed and {title_identities} title-identified forms; "
        f"removed {len(removed)} records"
    )


if __name__ == "__main__":
    main()
