#!/usr/bin/env python3
"""Snapshot live taxonomy candidates and build the staged classification sentinel."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import urlopen

PROMPTFOO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROMPTFOO_ROOT / "data"
SNAPSHOT_PATH = DATA_ROOT / "classification_taxonomy_snapshot.json"
OUTPUT_PATH = DATA_ROOT / "classification_sentinel_cases.jsonl"
REVIEWS_PATH = DATA_ROOT / "tyler_label_reviews.json"
CASES_PATH = DATA_ROOT / "cases.jsonl"
INPUTS_PATH = DATA_ROOT / "document_inputs.json"

CASE_SPECS = {
    "IL-02": {
        "variant": "flattened",
        "jurisdiction": "illinois",
        "court_code": "lake",
        "filing_phase": "initial",
        "levels": ["case category", "case type", "filing type"],
    },
    "IL-04": {
        "variant": "flattened",
        "jurisdiction": "illinois",
        "court_code": "kane",
        "filing_phase": "initial",
        "levels": ["case type"],
    },
    "IL-08": {
        "variant": "flattened",
        "jurisdiction": "illinois",
        "court_code": "madison",
        "filing_phase": "subsequent",
        "levels": ["case category"],
    },
    "IL-10": {
        "variant": "motion-facsimile",
        "jurisdiction": "illinois",
        "court_code": "sangamon",
        "filing_phase": "subsequent",
        "levels": ["case type", "filing type"],
    },
}

CLASSIFICATION_FIELDS = {"case category", "case type", "filing type"}


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def fetch(url):
    with urlopen(url, timeout=30) as response:  # noqa: S310 - endpoint is fixed in reviewed data
        items = json.load(response)
    return [{"code": str(item["code"]), "name": item["name"]} for item in items]


def candidate_url(base_url, spec, level, category=None, case_type=None):
    root = (
        f"{base_url}/jurisdictions/{spec['jurisdiction']}/codes/courts/"
        f"{quote(spec['court_code'], safe='')}"
    )
    if level == "case category":
        return f"{root}/categories?{urlencode({'fileable_only': 'true', 'timing': 'Initial'})}"
    if level == "case type":
        return f"{root}/case_types/?{urlencode({'category_id': category['code'], 'timing': 'Initial'})}"
    return f"{root}/filing_types/?" + urlencode(
        {
            "initial": str(spec["filing_phase"] == "initial").lower(),
            "category_id": category["code"],
            "type_id": case_type["code"],
        }
    )


def refresh_snapshot():
    review_document = json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))
    reviews = review_document["cases"]
    base_url = review_document["endpoint"].rstrip("/")
    snapshot_cases = []
    for case_id, spec in CASE_SPECS.items():
        case_review = reviews[case_id]
        category = case_review.get("case category", {}).get("tyler")
        case_type = case_review.get("case type", {}).get("tyler")
        for level in spec["levels"]:
            expected_review = case_review[level]
            expected = expected_review.get("tyler")
            expected_status = (
                "abstain" if expected_review.get("abstain") else "selected"
            )
            url = candidate_url(base_url, spec, level, category, case_type)
            candidates = fetch(url)
            if expected and not any(
                item["code"] == str(expected["code"])
                and item["name"] == expected["name"]
                for item in candidates
            ):
                raise RuntimeError(
                    f"Expected value missing from live candidates: {case_id} {level}"
                )
            snapshot_cases.append(
                {
                    "case_id": case_id,
                    "variant": spec["variant"],
                    "jurisdiction": spec["jurisdiction"],
                    "court_code": spec["court_code"],
                    "filing_phase": spec["filing_phase"],
                    "classification_level": level,
                    "selected_case_category": category,
                    "selected_case_type": case_type,
                    "expected_status": expected_status,
                    "expected_selection": expected,
                    "label_confidence": expected_review["confidence"],
                    "review_status": expected_review["review_status"],
                    "candidate_url": url,
                    "available_candidates": candidates,
                }
            )
    snapshot = {
        "schema_version": 1,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "endpoint": base_url,
        "reviewed_labels_at": review_document["reviewed_at"],
        "notes": "Live Tyler candidates for a small, hierarchical prompt ablation; this is not a permanent taxonomy.",
        "cases": snapshot_cases,
    }
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return snapshot


def direct_evidence(case):
    evidence = {}
    for key, target in case["vars"]["expected"].items():
        if key in CLASSIFICATION_FIELDS or target.get("source") != "document":
            continue
        accepted = target.get("accepted", [])
        if accepted:
            evidence[key] = accepted[0]
    return evidence


def first_three_pages(text):
    pages = text.split("\f")
    excerpt = "\f".join(pages[:3])
    if len(pages) <= 3:
        scope = f"all {len(pages)} MarkItDown page(s); no later text omitted"
    else:
        scope = f"first 3 of {len(pages)} MarkItDown pages; later pages omitted"
    return excerpt, scope


def build_cases(snapshot):
    source_cases = {
        (case["metadata"]["case_id"], case["metadata"]["variant"]): case
        for case in read_jsonl(CASES_PATH)
    }
    document_inputs = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))["documents"]
    output = []
    for item in snapshot["cases"]:
        key = (item["case_id"], item["variant"])
        source_case = source_cases[key]
        input_id = source_case["vars"]["document_input_id"]
        document_text, source_scope = first_three_pages(
            document_inputs[input_id]["markitdown_text"]
        )
        evidence = direct_evidence(source_case)
        evidence["filing phase"] = item["filing_phase"]
        output.append(
            {
                "description": (
                    f"{item['case_id']} {item['classification_level']}: "
                    f"{source_case['metadata']['form_name']}"
                ),
                "vars": {
                    "classification_level": item["classification_level"],
                    "jurisdiction": item["jurisdiction"],
                    "court_name": evidence.get("court", item["court_code"]),
                    "filing_phase": item["filing_phase"],
                    "selected_case_category": item["selected_case_category"] or {},
                    "selected_case_type": item["selected_case_type"] or {},
                    "available_candidates": item["available_candidates"],
                    "extracted_evidence": evidence,
                    "document_text": document_text,
                    "source_scope": source_scope,
                    "expected_status": item["expected_status"],
                    "expected_selection": item["expected_selection"] or {},
                },
                "metadata": {
                    "case_id": item["case_id"],
                    "variant": item["variant"],
                    "classification_level": item["classification_level"],
                    "court_code": item["court_code"],
                    "label_confidence": item["label_confidence"],
                    "review_status": item["review_status"],
                    "taxonomy_snapshot": SNAPSHOT_PATH.name,
                    "candidate_count": len(item["available_candidates"]),
                },
            }
        )
    return output


def render_jsonl(cases):
    return "".join(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n"
        for case in cases
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch and store current live candidate lists",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when generated cases do not match the snapshot",
    )
    args = parser.parse_args()
    if args.refresh:
        snapshot = refresh_snapshot()
    elif SNAPSHOT_PATH.exists():
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    else:
        raise SystemExit("No taxonomy snapshot; run with --refresh")

    rendered = render_jsonl(build_cases(snapshot))
    if args.check:
        existing = (
            OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        )
        if existing != rendered:
            raise SystemExit(
                "classification sentinel is out of date; run npm run refresh-classification-sentinel"
            )
        print(f"Validated {len(rendered.splitlines())} staged classification cases")
        return
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {len(snapshot['cases'])} taxonomy snapshots to {SNAPSHOT_PATH}")
    print(
        f"Wrote {len(rendered.splitlines())} staged classification cases to {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
