#!/usr/bin/env python3
"""Restore forms with no claimed ID when one local PDF has the exact title."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from audit_form_code_crosswalk import DEFAULT_CROSSWALK, expected_summary

ROOT = Path(__file__).resolve().parents[3]
FORMS_ROOT = ROOT / "court_forms"


def key(value: str) -> str:
    return re.sub(
        r"[\W_]+", "", unicodedata.normalize("NFKD", value).casefold(), flags=re.UNICODE
    )


def jurisdiction(value: str) -> str:
    return {"ma": "massachusetts", "il": "illinois", "vt": "vermont"}.get(
        value.casefold(), value.casefold()
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    args = parser.parse_args()

    current = json.loads(args.crosswalk.read_text(encoding="utf-8"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    titles = defaultdict(set)
    for row in json.loads(
        (FORMS_ROOT / "form_registry.json").read_text(encoding="utf-8")
    ):
        path = str(row.get("relative_path") or row.get("filename") or "")
        title = str(row.get("canonical_title") or row.get("title") or "")
        titles[
            (
                jurisdiction(str(row.get("jurisdiction") or path.split("/", 1)[0])),
                key(title),
            )
        ].add(path)

    current_ids = {entry["form"]["canonical_id"] for entry in current["registry"]}
    restore_ids = {
        entry["form"]["canonical_id"]
        for entry in baseline["registry"]
        if entry["form"]["canonical_id"] not in current_ids
        and not str(entry["form"].get("form_id") or "").strip()
        and entry["form"].get("is_form") is True
        and len(
            titles[
                (
                    entry["form"]["jurisdiction"],
                    key(entry["form"].get("canonical_name") or ""),
                )
            ]
        )
        == 1
    }
    current["registry"] = [
        entry
        for entry in baseline["registry"]
        if entry["form"]["canonical_id"] in current_ids | restore_ids
    ]
    current["summary"] = expected_summary(current)
    args.crosswalk.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Restored {len(restore_ids)} unique title-only forms")


if __name__ == "__main__":
    main()
