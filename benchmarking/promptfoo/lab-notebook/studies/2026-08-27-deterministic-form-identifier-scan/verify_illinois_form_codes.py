"""Verify the printed identifiers on the sampled Illinois forms."""

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
DEFAULT_MANIFEST = Path(__file__).with_name("illinois_form_code_verification.json")
DATASETS = {
    "official_templates": Path("benchmarking/synthetic/official_templates"),
    "interactive": Path("benchmarking/synthetic/filled_pdfs/interactive"),
    "flattened": Path("benchmarking/synthetic/filled_pdfs/flattened"),
}


def _normalized_identifier(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]", "", text)


def _first_matching_line(page_text: str, expected: str) -> str | None:
    needle = _normalized_identifier(expected)
    for line in page_text.splitlines():
        if needle in _normalized_identifier(line):
            return line.strip()
    return None


def _load_manifest(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload.get("samples", []) if isinstance(payload, dict) else []
    if not isinstance(samples, list) or not all(
        isinstance(sample, dict) for sample in samples
    ):
        raise ValueError(f"Manifest samples must be a list of objects: {path}")
    return samples


def _verify_sample(
    repo_root: Path,
    sample: dict[str, str],
    dataset: str,
    scan_document_for_form_identifiers,
) -> dict:
    sample_id = str(sample["sample_id"])
    path = repo_root / DATASETS[dataset] / f"{sample_id}.pdf"
    started = time.perf_counter()
    from pypdf import PdfReader

    pages = [(page.extract_text() or "") for page in PdfReader(path).pages]
    scan = scan_document_for_form_identifiers("illinois", "\f".join(pages))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    expected_identifier = str(sample["printed_identifier"])
    expected_normalized = _normalized_identifier(expected_identifier)
    observed_identifiers = {
        identifier
        for match in scan["matches"]
        for identifier in match["normalized_identifiers"]
    }
    deterministic = scan.get("deterministic_match") or {}
    passed = (
        expected_normalized in observed_identifiers
        and deterministic.get("canonical_form_id") == sample["canonical_form_id"]
        and deterministic.get("form_id") == sample["registry_form_id"]
    )
    return {
        "dataset": dataset,
        "sample_id": sample_id,
        "printed_identifier": expected_identifier,
        "revision": sample.get("revision"),
        "first_page_line": _first_matching_line(
            pages[0] if pages else "", expected_identifier
        ),
        "canonical_form_id": deterministic.get("canonical_form_id"),
        "registry_form_id": deterministic.get("form_id"),
        "scan_status": scan.get("status"),
        "elapsed_ms": elapsed_ms,
        "passed": passed,
        "source_url": sample.get("source_url"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", choices=sorted(DATASETS), action="append")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print machine-readable results",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    manifest_path = (
        args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    )
    datasets = args.dataset or list(DATASETS)

    app_root = repo_root / "efile_app"
    sys.path.insert(0, str(app_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "efile.settings_dev")

    import django

    django.setup()
    from efile.services.taxonomy_classification import (
        scan_document_for_form_identifiers,
    )

    results = []
    for dataset in datasets:
        for sample in _load_manifest(manifest_path):
            results.append(
                _verify_sample(
                    repo_root, sample, dataset, scan_document_for_form_identifiers
                )
            )

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        print(
            "dataset             sample  printed code   rev    canonical form       ms    result"
        )
        print(
            "------------------  ------  -------------  -----  --------------------  ----  ------"
        )
        for result in results:
            print(
                f"{result['dataset']:<18}  {result['sample_id']:<6}  "
                f"{result['printed_identifier']:<13}  {str(result['revision'] or ''):<5}  "
                f"{str(result['canonical_form_id'] or 'unmatched'):<20}  "
                f"{result['elapsed_ms']:>5.1f}  {'PASS' if result['passed'] else 'FAIL'}"
            )
        passed = sum(result["passed"] for result in results)
        print(f"\n{passed}/{len(results)} checks passed")
        failed = [result for result in results if not result["passed"]]
        if failed:
            print("Failures:")
            for result in failed:
                print(
                    f"  {result['dataset']}/{result['sample_id']}: {result['first_page_line']!r}"
                )
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
