#!/usr/bin/env python3
"""Add safe title identities and translated-title aliases to the crosswalk.

Printed form IDs remain the authoritative identity when available.  This tool
only uses titles in two narrower cases:

* a downloaded PDF is in an already verified printed-ID form family, in which
  case its registry title is an alternate title for that family; or
* several no-ID Vermont translations differ only by their explicit language
  label and have identical crosswalk mappings.  Those are one title-identified
  form, not several forms.

It also synchronizes the selected title-only records into the canonical-form
inventories, so the inventories and the production crosswalk agree.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from audit_form_code_crosswalk import DEFAULT_CROSSWALK, expected_summary
from prune_unverified_form_ids import ALLOWED_STATUSES

ROOT = Path(__file__).resolve().parents[3]
FORMS_ROOT = ROOT / "court_forms"
CANONICAL_FORMS_ROOT = DEFAULT_CROSSWALK.parent / "canonical_forms"
LANGUAGE_PREFIXES = {
    "arabic",
    "french",
    "nepali",
    "somali",
    "spanish",
    "swahili",
    "vietnamese",
}
NON_FORM_TITLE_KEYS = {"testdoc"}
LOW_SIGNAL_TITLE_KEYS = {
    "untitled",
    "viewform",
    "layout1",
    "kreyolayisyen",
    "portuguesportugal",
    "tiengviet",
}


def text_key(value: str | None) -> str:
    return re.sub(
        r"[\W_]+",
        "",
        unicodedata.normalize("NFKD", value or "").casefold(),
        flags=re.UNICODE,
    )


def jurisdiction(value: str | None) -> str:
    return {"ma": "massachusetts", "il": "illinois", "vt": "vermont"}.get(
        (value or "").casefold(), (value or "").casefold()
    )


def untranslated_title(title: str) -> str:
    """Remove only an explicit language label, never a substantive word."""
    first, separator, remainder = title.strip().partition(" ")
    return (
        remainder
        if separator and first.casefold() in LANGUAGE_PREFIXES
        else title.strip()
    )


def mapping_signature(entry: dict) -> str:
    return json.dumps(entry.get("mappings", []), ensure_ascii=False, sort_keys=True)


def add_alias(form: dict, title: str) -> None:
    title = title.strip()
    if not title:
        return
    aliases = form.setdefault("aliases", [])
    if not isinstance(aliases, list):
        aliases = form["aliases"] = []
    existing = {
        text_key(str(value)) for value in [form.get("canonical_name", ""), *aliases]
    }
    if text_key(title) not in existing:
        aliases.append(title)


def confirmed_family_titles(
    registry_rows: list[dict], id_index: dict
) -> dict[str, list[str]]:
    """Return local registry titles for each positively verified canonical ID."""
    titles_by_path = {
        str(row.get("relative_path") or row.get("filename") or ""): str(
            row.get("canonical_title") or row.get("title") or ""
        )
        for row in registry_rows
    }
    results = id_index.get("forms", {})
    titles: dict[str, list[str]] = {}
    for canonical_id, result in results.items():
        if not isinstance(result, dict) or result.get("status") not in ALLOWED_STATUSES:
            continue
        values = [
            titles_by_path.get(str(path), "")
            for path in result.get("candidate_paths", [])
        ]
        titles[str(canonical_id)] = [value for value in values if value]
    return titles


def consolidate_title_only_translations(entries: list[dict]) -> tuple[list[dict], int]:
    """Merge only unambiguous, same-mapping translation groups."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in entries:
        form = entry.get("form", {})
        if form.get("form_id"):
            continue
        title = str(form.get("canonical_name") or "")
        base = untranslated_title(title)
        if base != title:
            grouped[(str(form.get("jurisdiction") or ""), text_key(base))].append(entry)

    remove_ids: set[str] = set()
    replacements: dict[str, dict] = {}
    merged = 0
    for group in grouped.values():
        if len(group) < 2 or len({mapping_signature(entry) for entry in group}) != 1:
            continue
        first = copy.deepcopy(group[0])
        form = first["form"]
        base_title = untranslated_title(str(form.get("canonical_name") or ""))
        form["canonical_name"] = base_title
        form["identity_basis"] = "unique_title_translation_family"
        form["form_id"] = None
        form["aliases"] = []
        for entry in group:
            member_form = entry["form"]
            add_alias(form, str(member_form.get("canonical_name") or ""))
            for alias in member_form.get("aliases", []):
                add_alias(form, str(alias))
        keep_id = str(form["canonical_id"])
        replacements[keep_id] = first
        remove_ids.update(str(entry["form"]["canonical_id"]) for entry in group[1:])
        merged += len(group) - 1

    result = []
    for entry in entries:
        canonical_id = str(entry["form"]["canonical_id"])
        if canonical_id in remove_ids:
            continue
        result.append(replacements.get(canonical_id, entry))
    return result, merged


def remove_obvious_non_forms(entries: list[dict]) -> tuple[list[dict], int]:
    """Exclude downloader/test artifacts that are plainly not court forms."""
    retained = [
        entry
        for entry in entries
        if not (
            not entry["form"].get("form_id")
            and text_key(str(entry["form"].get("canonical_name") or ""))
            in NON_FORM_TITLE_KEYS
        )
    ]
    return retained, len(entries) - len(retained)


def import_downloaded_title_identities(
    entries: list[dict], registry_rows: list[dict], id_index: dict
) -> tuple[list[dict], int, int]:
    """Import every usable, currently-unrepresented no-ID downloaded title.

    These records intentionally have no filing mapping and no asserted form ID.
    They let the deterministic matcher report an exact title identity without
    pretending that title evidence establishes a Tyler filing route.
    """
    covered_paths = {
        str(path)
        for result in id_index.get("forms", {}).values()
        if isinstance(result, dict) and result.get("status") in ALLOWED_STATUSES
        for path in result.get("candidate_paths", [])
    }
    existing_titles = {
        (str(entry["form"].get("jurisdiction")), text_key(str(title)))
        for entry in entries
        for title in [
            entry["form"].get("canonical_name", ""),
            *entry["form"].get("aliases", []),
        ]
        if text_key(str(title))
    }
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    skipped = 0
    for row in registry_rows:
        path = str(row.get("relative_path") or row.get("filename") or "")
        title = str(row.get("canonical_title") or row.get("title") or "").strip()
        state = jurisdiction(str(row.get("jurisdiction") or path.split("/", 1)[0]))
        title_key = text_key(title)
        if (
            path in covered_paths
            or not title_key
            or (state, title_key) in existing_titles
        ):
            continue
        if title_key in LOW_SIGNAL_TITLE_KEYS:
            skipped += 1
            continue
        groups[(state, title_key)].append(row)

    imported = []
    prefixes = {"illinois": "IL", "massachusetts": "MA", "vermont": "VT"}
    for (state, title_key), rows in sorted(groups.items()):
        canonical_title = str(
            rows[0].get("canonical_title") or rows[0].get("title")
        ).strip()
        digest = hashlib.sha1(f"{state}:{title_key}".encode()).hexdigest()[:12].upper()
        aliases: list[str] = []
        for row in rows:
            title = str(row.get("canonical_title") or row.get("title") or "").strip()
            if text_key(title) != text_key(canonical_title) and title not in aliases:
                aliases.append(title)
        departments = {
            str(row.get("court_department") or "").strip()
            for row in rows
            if row.get("court_department")
        }
        source_urls = list(
            dict.fromkeys(
                str(row.get("source_url") or "").strip()
                for row in rows
                if row.get("source_url")
            )
        )
        unverified_registry_form_ids = list(
            dict.fromkeys(
                str(row.get("form_id") or "").strip()
                for row in rows
                if str(row.get("form_id") or "").strip()
            )
        )
        imported.append(
            {
                "form": {
                    "canonical_id": f"{prefixes.get(state, state.upper())}-TITLE-{digest}",
                    "jurisdiction": state,
                    "form_id": None,
                    "canonical_name": canonical_title,
                    "department": next(iter(departments))
                    if len(departments) == 1
                    else "General / Trial Court",
                    "description": "Downloaded court document identified by an exact title; no form ID or filing route has been asserted.",
                    "aliases": aliases,
                    "official": True,
                    "is_form": True,
                    "revision": None,
                    "document_role": "court_form",
                    "identity_basis": (
                        "downloaded_title_with_unverified_registry_id"
                        if unverified_registry_form_ids
                        else "unique_downloaded_title"
                    ),
                    "unverified_registry_form_ids": unverified_registry_form_ids,
                    "source_urls": source_urls,
                },
                "mappings": [],
            }
        )
    return [*entries, *imported], len(imported), skipped


def merge_duplicate_canonical_ids(entries: list[dict]) -> tuple[list[dict], int]:
    """Repair legacy title-key changes by folding duplicate generated IDs."""
    merged: dict[str, dict] = {}
    duplicates = 0
    for entry in entries:
        canonical_id = str(entry["form"]["canonical_id"])
        existing = merged.get(canonical_id)
        if existing is None:
            merged[canonical_id] = entry
            continue
        # Generated title identities have no mappings. If a normalization change
        # makes a formerly collapsed translated title distinct, retain both
        # source URLs and titles under the pre-existing stable ID.
        if existing.get("mappings") or entry.get("mappings"):
            raise ValueError(f"Duplicate mapped canonical ID: {canonical_id}")
        existing_form = existing["form"]
        incoming_form = entry["form"]
        add_alias(existing_form, str(incoming_form.get("canonical_name") or ""))
        for alias in incoming_form.get("aliases", []):
            add_alias(existing_form, str(alias))
        existing_form["source_urls"] = list(
            dict.fromkeys(
                [
                    *existing_form.get("source_urls", []),
                    *incoming_form.get("source_urls", []),
                ]
            )
        )
        duplicates += 1
    return list(merged.values()), duplicates


def sync_canonical_inventories(
    entries: list[dict], check: bool
) -> list[tuple[Path, str]]:
    by_jurisdiction: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        form = entry.get("form", {})
        if form.get("is_form"):
            by_jurisdiction[str(form.get("jurisdiction"))].append(form)
    changes = []
    for path in sorted(CANONICAL_FORMS_ROOT.glob("*_forms.json")):
        state = path.stem.removesuffix("_forms")
        selected = by_jurisdiction.get(state, [])
        old = json.loads(path.read_text(encoding="utf-8"))
        old_ids = {str(form.get("canonical_id")) for form in old}
        replacement = [copy.deepcopy(form) for form in selected]
        # The inventories are the source of forms, so stale non-selected records
        # intentionally stay out after printed-ID/title-identity curation.
        del old_ids
        rendered = json.dumps(replacement, ensure_ascii=False, indent=2) + "\n"
        if rendered != path.read_text(encoding="utf-8"):
            changes.append((path, rendered))
    if not check:
        for path, content in changes:
            path.write_text(content, encoding="utf-8")
    return changes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    document = json.loads(args.crosswalk.read_text(encoding="utf-8"))
    registry_rows = json.loads(
        (FORMS_ROOT / "form_registry.json").read_text(encoding="utf-8")
    )
    id_index = json.loads(
        (FORMS_ROOT / "form_id_matches.json").read_text(encoding="utf-8")
    )
    family_titles = confirmed_family_titles(registry_rows, id_index)

    for entry in document["registry"]:
        form = entry["form"]
        for title in family_titles.get(str(form.get("canonical_id")), []):
            add_alias(form, title)
        if not form.get("form_id"):
            form.setdefault("identity_basis", "unique_title")

    document["registry"], merged = consolidate_title_only_translations(
        document["registry"]
    )
    document["registry"], removed_non_forms = remove_obvious_non_forms(
        document["registry"]
    )
    document["registry"], imported_titles, skipped_low_signal_titles = (
        import_downloaded_title_identities(
            document["registry"], registry_rows, id_index
        )
    )
    document["registry"], merged_duplicate_ids = merge_duplicate_canonical_ids(
        document["registry"]
    )
    document["summary"] = expected_summary(document)
    changelog = document.setdefault("changelog", [])
    if not any(
        item.get("version") == "1.4.0" for item in changelog if isinstance(item, dict)
    ):
        changelog.insert(
            0,
            {
                "version": "1.4.0",
                "date": "2026-08-28",
                "changes": [
                    "Imported unique title-only downloaded forms into the canonical inventories without assigning an unproven form ID.",
                    "Added downloaded translated and revised titles as aliases of their verified printed-ID form family.",
                    "Consolidated exact title-only language variants with identical mappings into one title-identified form.",
                    "Imported usable downloaded titles with no asserted form ID as unmapped title identities.",
                ],
            },
        )
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    canonical_changes = sync_canonical_inventories(document["registry"], args.check)
    if args.check:
        if rendered != args.crosswalk.read_text(encoding="utf-8") or canonical_changes:
            raise SystemExit("Title identities are not synchronized")
        print("Title identities are synchronized")
        return
    args.crosswalk.write_text(rendered, encoding="utf-8")
    print(
        f"Synchronized {len(document['registry'])} forms; consolidated {merged} translated title-only records; "
        f"removed {removed_non_forms} obvious non-form artifacts; "
        f"imported {imported_titles} downloaded title identities; skipped {skipped_low_signal_titles} low-signal titles; "
        f"merged {merged_duplicate_ids} duplicate title identities; "
        f"updated {len(canonical_changes)} canonical inventories"
    )


if __name__ == "__main__":
    main()
