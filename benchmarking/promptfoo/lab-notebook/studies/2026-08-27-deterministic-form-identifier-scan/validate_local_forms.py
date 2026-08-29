"""Validate deterministic form-identifier scanning against the local PDF corpus."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_ILLINOIS_MANIFEST = Path(__file__).with_name(
    "illinois_form_code_verification.json"
)


def _normalized_identifier(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]", "", text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    app_root = repo_root / "efile_app"
    sys.path.insert(0, str(app_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "efile.settings_dev")

    import django
    from pypdf import PdfReader

    django.setup()
    from efile.services.taxonomy_classification import (
        scan_document_for_form_identifiers,
    )

    records = {
        row["id"]: row
        for row in (
            json.loads(line)
            for line in (repo_root / "benchmarking/synthetic/extractability.jsonl")
            .read_text()
            .splitlines()
        )
    }
    illinois_manifest = {
        sample["sample_id"]: sample
        for sample in json.loads(DEFAULT_ILLINOIS_MANIFEST.read_text(encoding="utf-8"))[
            "samples"
        ]
    }
    results = []
    for dataset in (
        "official_templates",
        "filled_pdfs/interactive",
        "filled_pdfs/flattened",
    ):
        durations = []
        expected_present = 0
        deterministic_count = 0
        expected_deterministic = 0
        mismatches = []
        for case_id, record in sorted(records.items()):
            path = repo_root / "benchmarking/synthetic" / dataset / f"{case_id}.pdf"
            started = time.perf_counter()
            text = "\f".join(
                page.extract_text() or "" for page in PdfReader(path).pages
            )
            scan = scan_document_for_form_identifiers(record["jurisdiction"], text)
            elapsed_ms = (time.perf_counter() - started) * 1000
            durations.append(elapsed_ms)

            expected_sample = illinois_manifest.get(case_id)
            expected = _normalized_identifier(
                expected_sample["printed_identifier"]
                if expected_sample
                else record["form_number"]
            )
            found = {
                identifier
                for match in scan["matches"]
                for identifier in match["normalized_identifiers"]
            }
            deterministic_match = scan.get("deterministic_match") or {}
            deterministic_id = _normalized_identifier(
                deterministic_match.get("form_id", "")
            )
            deterministic_canonical_id = deterministic_match.get("canonical_form_id")
            expected_was_present = expected in found
            if expected_was_present:
                expected_present += 1
            if deterministic_id:
                deterministic_count += 1
            deterministic_is_expected = (
                deterministic_canonical_id == expected_sample["canonical_form_id"]
                if expected_sample
                else expected == deterministic_id
            )
            if deterministic_is_expected:
                expected_deterministic += 1
            elif deterministic_id or expected_was_present:
                mismatches.append(
                    {
                        "id": case_id,
                        "expected": expected_sample["printed_identifier"]
                        if expected_sample
                        else record["form_number"],
                        "status": scan["status"],
                        "deterministic": deterministic_match.get("form_id"),
                        "deterministic_canonical_id": deterministic_canonical_id,
                        "found": sorted(found),
                    }
                )

        results.append(
            {
                "dataset": dataset,
                "documents": len(records),
                "expected_identifier_present": expected_present,
                "deterministic": deterministic_count,
                "expected_deterministic": expected_deterministic,
                "max_pdf_text_and_scan_ms": round(max(durations), 2),
                "average_pdf_text_and_scan_ms": round(
                    sum(durations) / len(durations), 2
                ),
                "mismatches": mismatches,
            }
        )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
