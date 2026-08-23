#!/usr/bin/env python3
"""Snapshot live candidates and build a stratified staged-classification study."""

import argparse
import json
import re
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
CROSSWALK_PATH = DATA_ROOT / "form_code_crosswalk.json"

# Six decisions per jurisdiction, spanning category, case-type, and filing-type
# selection. Parent levels are resolved live by durable name even when the parent
# is not itself an evaluated decision.
CASE_SPECS = {
    "MA-01": {
        "variant": "flattened",
        "jurisdiction": "massachusetts",
        "court_code": "344",
        "filing_phase": "initial",
        "levels": ["case category", "case type", "filing type"],
    },
    "MA-05": {
        "variant": "flattened",
        "jurisdiction": "massachusetts",
        "court_code": "348",
        "filing_phase": "initial",
        "levels": ["filing type"],
    },
    "MA-06": {
        "variant": "flattened",
        "jurisdiction": "massachusetts",
        "court_code": "490",
        "filing_phase": "initial",
        "levels": ["case type", "filing type"],
    },
    "VT-01": {
        "variant": "flattened",
        "jurisdiction": "vermont",
        "court_code": "sc:chittendon",
        "filing_phase": "initial",
        "levels": ["case category", "case type", "filing type"],
    },
    "VT-03": {
        "variant": "flattened",
        "jurisdiction": "vermont",
        "court_code": "sc:washington",
        "filing_phase": "initial",
        "levels": ["case type", "filing type"],
    },
    "VT-06": {
        "variant": "flattened",
        "jurisdiction": "vermont",
        "court_code": "sc:addison",
        "filing_phase": "initial",
        "levels": ["filing type"],
    },
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
        "levels": ["filing type"],
    },
}

CLASSIFICATION_FIELDS = {"case category", "case type", "filing type"}


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalize(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def fetch(url):
    with urlopen(url, timeout=30) as response:  # noqa: S310 - endpoint comes from reviewed data
        items = json.load(response)
    return [{"code": str(item["code"]), "name": item["name"].strip()} for item in items]


def candidate_url(base_url, spec, level, category=None, case_type=None):
    root = f"{base_url}/jurisdictions/{spec['jurisdiction']}/codes/courts/{quote(spec['court_code'], safe='')}"
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


def accepted_names(review):
    return [str(name).strip() for name in review.get("accepted", [])]


def resolve(candidates, review, case_id, level):
    names = accepted_names(review)
    matches = [item for item in candidates if item["name"] in names]
    if names and len(matches) != len(names):
        missing = sorted(set(names) - {item["name"] for item in matches})
        raise RuntimeError(
            f"Durable names missing from live candidates: {case_id} {level}: {missing}"
        )
    return matches


def refresh_snapshot():
    review_document = json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))
    reviews = review_document["cases"]
    base_url = review_document["endpoint"].rstrip("/")
    snapshot_cases = []
    for case_id, spec in CASE_SPECS.items():
        fields = reviews[case_id]
        category_url = candidate_url(base_url, spec, "case category")
        categories = fetch(category_url)
        category_matches = resolve(
            categories, fields.get("case category", {}), case_id, "case category"
        )
        category = category_matches[0] if category_matches else None

        case_types = []
        type_matches = []
        case_type = None
        type_url = None
        if category:
            type_url = candidate_url(base_url, spec, "case type", category)
            case_types = fetch(type_url)
            type_matches = resolve(
                case_types, fields.get("case type", {}), case_id, "case type"
            )
            case_type = type_matches[0] if type_matches else None

        filing_types = []
        filing_matches = []
        filing_url = None
        if category and case_type:
            filing_url = candidate_url(
                base_url, spec, "filing type", category, case_type
            )
            filing_types = fetch(filing_url)
            filing_matches = resolve(
                filing_types, fields.get("filing type", {}), case_id, "filing type"
            )

        level_data = {
            "case category": (category_url, categories, category_matches),
            "case type": (type_url, case_types, type_matches),
            "filing type": (filing_url, filing_types, filing_matches),
        }
        for level in spec["levels"]:
            review = fields[level]
            url, candidates, expected_matches = level_data[level]
            expected_status = "abstain" if review.get("abstain") else "selected"
            if expected_status == "selected" and not expected_matches:
                raise RuntimeError(f"No current expected value for {case_id} {level}")
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
                    "expected_names": accepted_names(review),
                    "label_confidence": review["confidence"],
                    "review_status": review["review_status"],
                    "candidate_url": url,
                    "available_candidates": candidates,
                }
            )
    snapshot = {
        "schema_version": 2,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "endpoint": base_url,
        "reviewed_labels_at": review_document["reviewed_at"],
        "notes": (
            "Durable gold identity is the exact normalized Tyler name. Codes in this snapshot are "
            "transient route keys used only to reproduce the catalog response."
        ),
        "strata": {
            "jurisdiction": {"massachusetts": 6, "vermont": 6, "illinois": 6},
            "classification_level": {
                "case category": 4,
                "case type": 6,
                "filing type": 8,
            },
        },
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
    scope = (
        f"all {len(pages)} MarkItDown page(s); no later text omitted"
        if len(pages) <= 3
        else f"first 3 of {len(pages)} MarkItDown pages; later pages omitted"
    )
    return excerpt, scope


def crosswalk_index():
    crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    index = {}
    for entry in crosswalk["registry"]:
        form = entry["form"]
        for value in [
            form.get("form_id"),
            form.get("canonical_name"),
            *form.get("aliases", []),
        ]:
            if value:
                index.setdefault((form["jurisdiction"], normalize(value)), []).append(
                    entry
                )
    return index


def crosswalk_candidates(source_case, index):
    expected = source_case["vars"]["expected"]
    jurisdiction = source_case["metadata"]["jurisdiction"]
    values = [source_case["metadata"]["form_name"]]
    values.extend(expected.get("form identifier", {}).get("accepted", []))
    entries = []
    seen_entries = set()
    for value in values:
        for entry in index.get((jurisdiction, normalize(value)), []):
            canonical_id = entry["form"]["canonical_id"]
            if canonical_id not in seen_entries:
                entries.append(entry)
                seen_entries.add(canonical_id)
    suggestions = []
    seen = set()
    for entry in entries:
        for mapping in entry.get("mappings", []):
            if mapping.get("catalog_status") not in {"current", "partial_observation"}:
                continue
            if float(mapping.get("confidence", 0)) < 0.85:
                continue
            suggestion = {
                "matched_form_id": entry["form"].get("form_id"),
                "matched_form_name": entry["form"]["canonical_name"],
                "filing_phase": mapping.get("filing_phase"),
                "category": mapping.get("category"),
                "case_type": mapping.get("case_type"),
                "filing_type": mapping.get("filing_type"),
                "association_status": mapping.get("association_status"),
                "confidence": mapping.get("confidence"),
            }
            key = json.dumps(suggestion, sort_keys=True)
            if key not in seen:
                suggestions.append(suggestion)
                seen.add(key)
    return suggestions[:12]


def build_cases(snapshot):
    source_cases = {
        (case["metadata"]["case_id"], case["metadata"]["variant"]): case
        for case in read_jsonl(CASES_PATH)
    }
    document_inputs = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))["documents"]
    form_index = crosswalk_index()
    output = []
    for item in snapshot["cases"]:
        source_case = source_cases[(item["case_id"], item["variant"])]
        input_id = source_case["vars"]["document_input_id"]
        document_text, source_scope = first_three_pages(
            document_inputs[input_id]["markitdown_text"]
        )
        evidence = direct_evidence(source_case)
        evidence["filing phase"] = item["filing_phase"]
        expected_names = item["expected_names"]
        level = item["classification_level"]
        selected_category = (
            item["selected_case_category"] if level != "case category" else {}
        )
        selected_type = item["selected_case_type"] if level == "filing type" else {}
        output.append(
            {
                "description": f"{item['case_id']} {item['classification_level']}: {source_case['metadata']['form_name']}",
                "vars": {
                    "classification_level": item["classification_level"],
                    "jurisdiction": item["jurisdiction"],
                    "court_name": evidence.get("court", item["court_code"]),
                    "filing_phase": item["filing_phase"],
                    "selected_case_category": selected_category or {},
                    "selected_case_type": selected_type or {},
                    "available_candidates": item["available_candidates"],
                    "extracted_evidence": evidence,
                    "form_identity": {
                        "name": evidence.get("form name"),
                        "identifier": evidence.get("form identifier"),
                    },
                    "crosswalk_candidates": crosswalk_candidates(
                        source_case, form_index
                    ),
                    "document_text": document_text,
                    "source_scope": source_scope,
                    "expected_status": item["expected_status"],
                    "expected_names": expected_names,
                },
                "metadata": {
                    "case_id": item["case_id"],
                    "variant": item["variant"],
                    "jurisdiction": item["jurisdiction"],
                    "classification_level": item["classification_level"],
                    "court_code": item["court_code"],
                    "label_confidence": item["label_confidence"],
                    "review_status": item["review_status"],
                    "taxonomy_snapshot": SNAPSHOT_PATH.name,
                    "candidate_count": len(item["available_candidates"]),
                    "crosswalk_suggestion_count": len(
                        crosswalk_candidates(source_case, form_index)
                    ),
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
            raise SystemExit("classification sentinel is out of date; refresh it")
        print(f"Validated {len(rendered.splitlines())} staged classification cases")
        return
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {len(snapshot['cases'])} taxonomy snapshots to {SNAPSHOT_PATH}")
    print(
        f"Wrote {len(rendered.splitlines())} staged classification cases to {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
