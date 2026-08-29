#!/usr/bin/env python3
"""Explain downloaded PDFs that are not yet represented by a safe crosswalk identity."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from audit_form_code_crosswalk import DEFAULT_CROSSWALK
from prune_unverified_form_ids import ALLOWED_STATUSES

ROOT = Path(__file__).resolve().parents[3]
FORMS_ROOT = ROOT / "court_forms"
LANGUAGE_PREFIXES = {
    "arabic",
    "french",
    "nepali",
    "somali",
    "spanish",
    "swahili",
    "vietnamese",
}


def key(value: str | None) -> str:
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


def stripped_language_title(title: str) -> str:
    first, separator, remainder = title.strip().partition(" ")
    return (
        remainder
        if separator and first.casefold() in LANGUAGE_PREFIXES
        else title.strip()
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "benchmarking/promptfoo/lab-notebook/reviews/2026-08-27-crosswalk-field-review-tool/artifacts/unrecognized-local-forms.json",
    )
    args = parser.parse_args()

    crosswalk = json.loads(args.crosswalk.read_text(encoding="utf-8"))
    local_rows = json.loads(
        (FORMS_ROOT / "form_registry.json").read_text(encoding="utf-8")
    )
    id_index = json.loads(
        (FORMS_ROOT / "form_id_matches.json").read_text(encoding="utf-8")
    )
    covered_paths = {
        str(path)
        for result in id_index.get("forms", {}).values()
        if isinstance(result, dict) and result.get("status") in ALLOWED_STATUSES
        for path in result.get("candidate_paths", [])
    }
    aliases: dict[tuple[str, str], set[str]] = defaultdict(set)
    claimed_ids: dict[str, bool] = {}
    for entry in crosswalk["registry"]:
        form = entry["form"]
        claimed_ids[str(form["canonical_id"])] = bool(form.get("form_id"))
        for title in [form.get("canonical_name", ""), *form.get("aliases", [])]:
            if key(str(title)):
                aliases[(str(form["jurisdiction"]), key(str(title)))].add(
                    str(form["canonical_id"])
                )

    categories: dict[str, list[dict]] = defaultdict(list)
    for row in local_rows:
        path = str(row.get("relative_path") or row.get("filename") or "")
        if path in covered_paths:
            continue
        state = jurisdiction(str(row.get("jurisdiction") or path.split("/", 1)[0]))
        title = str(row.get("canonical_title") or row.get("title") or "").strip()
        title_matches = aliases.get((state, key(title)), set())
        base = stripped_language_title(title)
        base_matches = (
            aliases.get((state, key(base)), set()) if base != title else set()
        )
        item = {
            "path": path,
            "jurisdiction": state,
            "title": title,
            "registry_form_id": row.get("form_id") or None,
            "language": row.get("language") or None,
            "source_url": row.get("source_url") or None,
        }
        if len(title_matches) == 1:
            item["canonical_id"] = next(iter(title_matches))
            category = (
                "title_alias_needs_id_confirmation"
                if claimed_ids[item["canonical_id"]]
                else "represented_title_only_identity"
            )
            categories[category].append(item)
        elif len(base_matches) == 1:
            item["canonical_id"] = next(iter(base_matches))
            categories["language_title_needs_alias_review"].append(item)
        elif row.get("form_id"):
            categories["unverified_registry_id"].append(item)
        elif title:
            category = (
                "low_signal_title_metadata"
                if key(title)
                in {
                    "untitled",
                    "viewform",
                    "layout1",
                    "kreyolayisyen",
                    "portuguesportugal",
                    "tiengviet",
                }
                else "unique_title_candidate"
            )
            categories[category].append(item)
        else:
            categories["missing_title_and_id"].append(item)

    payload = {
        "description": (
            "Downloaded PDFs not covered by the exact printed-ID reverse index. "
            "A registry-supplied ID is not treated as identity evidence until it is printed in the PDF."
        ),
        "total_local_pdfs": len(local_rows),
        "printed_id_covered_pdfs": len(covered_paths),
        "remaining_pdfs": sum(len(items) for items in categories.values()),
        "counts": dict(
            sorted((name, len(items)) for name, items in categories.items())
        ),
        "by_jurisdiction": {
            name: dict(sorted(Counter(item["jurisdiction"] for item in items).items()))
            for name, items in sorted(categories.items())
        },
        "forms": dict(sorted(categories.items())),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"counts": payload["counts"], "remaining_pdfs": payload["remaining_pdfs"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
