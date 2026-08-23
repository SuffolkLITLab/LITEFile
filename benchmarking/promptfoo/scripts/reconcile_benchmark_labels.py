#!/usr/bin/env python3
"""Reconcile synthetic taxonomy labels with live reviews and the form crosswalk."""

import argparse
import csv
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path

PROMPTFOO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROMPTFOO_ROOT / "data"
REVIEWS_PATH = DATA_ROOT / "tyler_label_reviews.json"
CASES_PATH = DATA_ROOT / "cases.jsonl"
CROSSWALK_PATH = DATA_ROOT / "form_code_crosswalk.json"

CORRECTIONS = {
    "MA-01": {
        "case category": (
            "Domestic Relations",
            0.98,
            "verified_live_crosswalk_supported",
        ),
        "case type": ("Divorce 1B", 0.98, "verified_live_crosswalk_supported"),
        "filing type": (
            "Complaint for Divorce - Irretrievable Breakdown 1B",
            0.98,
            "verified_live_crosswalk_supported",
        ),
    },
    "MA-02": {
        "case category": (
            "Joint Petition (1A)",
            0.98,
            "verified_live_crosswalk_supported",
        ),
        "case type": ("Joint Petition (1A)", 0.98, "verified_live_crosswalk_supported"),
        "filing type": (
            "Joint Petition for Divorce",
            0.98,
            "verified_live_crosswalk_supported",
        ),
    },
    "MA-03": {
        "case category": (
            "Custody, Support, Parenting Time",
            0.98,
            "verified_live_crosswalk_supported",
        ),
        "case type": (
            "Complaint For Custody, Support, Parenting Time",
            0.98,
            "verified_live_crosswalk_supported",
        ),
        "filing type": (
            "Complaint for Custody, Support, Parenting Time",
            0.98,
            "verified_live_crosswalk_supported",
        ),
    },
    "MA-05": {
        "case category": ("Change of Name", 0.98, "verified_live_form_supported"),
        "case type": ("Petition for Adult", 0.98, "verified_live_form_supported"),
        "filing type": (
            "Petition to Change Name of Adult",
            0.98,
            "verified_live_form_supported",
        ),
    },
    "MA-06": {
        "case category": ("Small Claims", 0.98, "verified_live_document_supported"),
        "case type": (
            "Small Claim $501 - $2000",
            0.98,
            "verified_live_document_supported",
        ),
        "filing type": (
            "Statement of Small Claims entered through e-file process",
            0.98,
            "verified_live_document_supported",
        ),
    },
    "VT-01": {
        "filing type": ("Initial Filing", 0.78, "verified_live_generic_filing_label"),
    },
    "VT-02": {
        "filing type": ("Initial Filing", 0.78, "verified_live_generic_filing_label"),
    },
    "VT-03": {
        "filing type": (
            "Small Claims Complaint $1000 - $5000",
            0.94,
            "verified_live_document_supported",
        ),
    },
    "VT-05": {
        "filing type": ("Initial Filing", 0.72, "verified_live_generic_filing_label"),
    },
    "VT-06": {
        "filing type": ("Initial Filing", 0.72, "verified_live_generic_filing_label"),
    },
    "VT-07": {
        "filing type": ("Initial Filing", 0.72, "verified_live_generic_filing_label"),
    },
}

CORRECTION_NOTES = {
    "MA-01": "Exact official-form match and exact current live hierarchy.",
    "MA-02": "Exact official-form match and exact current live hierarchy.",
    "MA-03": "Exact official-form match and exact current live hierarchy.",
    "MA-05": "Exact form identity plus current live hierarchy; Tyler whitespace is normalized.",
    "MA-06": "The document's $1,275 claim selects the live amount band.",
    "VT-01": "The exact form title is retained separately; Tyler exposes the generic Initial Filing value.",
    "VT-02": "The exact form title is retained separately; Tyler exposes the generic Initial Filing value.",
    "VT-03": "The document's $2,250 claim selects the live filing-name amount band.",
    "VT-05": "The exact form title is retained separately; Tyler exposes the generic Initial Filing value.",
    "VT-06": "The exact form title is retained separately; Tyler exposes the generic Initial Filing value.",
    "VT-07": "The exact form title is retained separately; Tyler exposes the generic Initial Filing value.",
}

UNRESOLVED = {
    "MA-04": {
        "case category": "The live catalog has no distinct separate-support category.",
        "case type": "The crosswalk points to custody/support/parenting time, but that is not a safe semantic match.",
        "filing type": "No current live filing name specifically identifies a separate-support complaint.",
    }
}


def normalize(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def migrate_review_schema(document):
    """Move transient Tyler numeric keys into dated catalog observations."""
    migrated = deepcopy(document)
    for fields in migrated["cases"].values():
        for review in fields.values():
            selections = review.pop("accepted_tylers", [])
            primary = review.pop("tyler", None)
            if primary:
                review.setdefault("preferred_name", primary["name"].strip())
                selections.insert(0, primary)
            observations = (
                review.setdefault("catalog_observations", []) if selections else []
            )
            seen = {
                (item.get("name"), str(item.get("transient_key")))
                for item in observations
            }
            for selection in selections:
                observation = {
                    "environment": "test",
                    "observed_at": migrated["reviewed_at"],
                    "name": selection["name"].strip(),
                    "transient_key": str(selection["code"]),
                }
                key = (observation["name"], observation["transient_key"])
                if key not in seen:
                    observations.append(observation)
                    seen.add(key)
    return migrated


def apply_corrections(document):
    corrected = migrate_review_schema(document)
    for case_id, fields in CORRECTIONS.items():
        case = corrected["cases"].setdefault(case_id, {})
        for field, (name, confidence, status) in fields.items():
            old_observations = case.get(field, {}).get("catalog_observations", [])
            case[field] = {
                "accepted": [name],
                "preferred_name": name,
                "confidence": confidence,
                "review_status": status,
                "catalog_observations": old_observations,
                "notes": CORRECTION_NOTES[case_id],
            }
    for case_id, fields in UNRESOLVED.items():
        case = corrected["cases"].setdefault(case_id, {})
        for field, note in fields.items():
            case[field] = {
                "required": False,
                "abstain": True,
                "confidence": 0.95,
                "review_status": "crosswalk_conflict_unresolved",
                "notes": note,
            }
    corrected["schema_version"] = 2
    corrected["notes"] = (
        "Durable Tyler identities are exact normalized names. Numeric keys are dated, "
        "environment-specific observations only. Unlisted cases retain lower-confidence synthetic labels."
    )
    return corrected


def crosswalk_index(crosswalk):
    by_id = {}
    by_name = {}
    for entry in crosswalk["registry"]:
        form = entry["form"]
        if form.get("form_id"):
            by_id.setdefault(normalize(form["form_id"]), []).append(entry)
        by_name.setdefault(normalize(form["canonical_name"]), []).append(entry)
    return by_id, by_name


def reconcile_rows(reviews, crosswalk):
    by_id, by_name = crosswalk_index(crosswalk)
    seen = set()
    rows = []
    for case in read_jsonl(CASES_PATH):
        case_id = case["metadata"]["case_id"]
        if case_id in seen:
            continue
        seen.add(case_id)
        expected = case["vars"]["expected"]
        form_id = (expected.get("form identifier", {}).get("accepted") or [""])[0]
        form_name = case["metadata"]["form_name"]
        matches = by_id.get(normalize(form_id), []) or by_name.get(
            normalize(form_name), []
        )
        review = reviews["cases"].get(case_id, {})
        mappings = [
            mapping for entry in matches for mapping in entry.get("mappings", [])
        ]
        for field, mapping_key in (
            ("case category", "category"),
            ("case type", "case_type"),
            ("filing type", "filing_type"),
        ):
            accepted = review.get(field, {}).get("accepted", [])
            current_values = sorted(
                {
                    mapping[mapping_key].strip()
                    for mapping in mappings
                    if mapping.get(mapping_key)
                    and mapping.get("catalog_status")
                    in {"current", "partial_observation"}
                }
            )
            accepted_normalized = {normalize(value) for value in accepted}
            current_normalized = {normalize(value) for value in current_values}
            if not matches:
                result = "no_crosswalk_match"
            elif not accepted:
                result = "benchmark_unresolved"
            elif accepted_normalized & current_normalized:
                result = "agrees"
            elif current_values:
                result = "conflict"
            else:
                result = "crosswalk_unresolved"
            rows.append(
                {
                    "case_id": case_id,
                    "jurisdiction": case["metadata"]["jurisdiction"],
                    "form_id": form_id,
                    "form_name": form_name,
                    "crosswalk_matches": len(matches),
                    "field": field,
                    "accepted_names": " | ".join(accepted),
                    "current_crosswalk_names": " | ".join(current_values),
                    "result": result,
                    "label_confidence": review.get(field, {}).get("confidence", ""),
                    "review_status": review.get(field, {}).get("review_status", ""),
                }
            )
    return rows


def write_report(output_dir, rows):
    output_dir.mkdir(parents=True, exist_ok=True)
    table_dir = output_dir / "tables"
    artifact_dir = output_dir / "artifacts"
    table_dir.mkdir(exist_ok=True)
    artifact_dir.mkdir(exist_ok=True)
    with (table_dir / "label-reconciliation.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "rows": len(rows),
        "cases": len({row["case_id"] for row in rows}),
        "result_counts": dict(sorted(Counter(row["result"] for row in rows).items())),
        "crosswalk_matched_cases": len(
            {row["case_id"] for row in rows if row["crosswalk_matches"]}
        ),
    }
    (artifact_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply reviewed corrections and schema migration",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    reviews = json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))
    if args.apply:
        reviews = apply_corrections(reviews)
        REVIEWS_PATH.write_text(
            json.dumps(reviews, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    rows = reconcile_rows(reviews, crosswalk)
    summary = (
        write_report(args.output_dir, rows)
        if args.output_dir
        else {"result_counts": dict(Counter(row["result"] for row in rows))}
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
