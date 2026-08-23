#!/usr/bin/env python3
"""Check durable reviewed Tyler names against the current efile-test code lists."""

import json
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import urlopen

PROMPTFOO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = PROMPTFOO_ROOT / "data" / "tyler_label_reviews.json"

COURT_CODES = {
    "IL-02": ("illinois", "lake"),
    "IL-03": ("illinois", "champaign"),
    "IL-04": ("illinois", "kane"),
    "IL-05": ("illinois", "mclean"),
    "IL-06": ("illinois", "winnebago"),
    "IL-07": ("illinois", "peoria"),
    "IL-08": ("illinois", "madison"),
    "IL-10": ("illinois", "sangamon"),
    "MA-01": ("massachusetts", "344"),
    "MA-02": ("massachusetts", "346"),
    "MA-03": ("massachusetts", "339"),
    "MA-05": ("massachusetts", "348"),
    "MA-06": ("massachusetts", "490"),
    "MA-07": ("massachusetts", "537"),
    "VT-01": ("vermont", "sc:chittendon"),
    "VT-02": ("vermont", "sc:rutland"),
    "VT-03": ("vermont", "sc:washington"),
    "VT-04": ("vermont", "sc:windham"),
    "VT-05": ("vermont", "sc:franklin"),
    "VT-06": ("vermont", "sc:addison"),
    "VT-07": ("vermont", "sc:orange"),
    "VT-08": ("vermont", "sc:chittendon"),
    "VT-09": ("vermont", "sc:washington"),
    "VT-10": ("vermont", "sc:bennington"),
}

SUBSEQUENT_CASES = {"IL-08", "IL-10", "VT-04", "VT-08", "VT-09", "VT-10"}


def fetch(url):
    with urlopen(url, timeout=20) as response:  # noqa: S310 - fixed, reviewed endpoint
        return [
            {"code": str(item["code"]), "name": item["name"].strip()}
            for item in json.load(response)
        ]


def resolve_names(items, names):
    by_name = {item["name"]: item for item in items}
    return [by_name[name] for name in names if name in by_name]


def accepted_names(review):
    return [str(name).strip() for name in review.get("accepted", [])]


def main():
    document = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    base_url = document["endpoint"].rstrip("/")
    failures = []
    checked = 0

    for case_id, fields in document["cases"].items():
        if case_id not in COURT_CODES:
            continue
        jurisdiction, court = COURT_CODES[case_id]
        root = f"{base_url}/jurisdictions/{jurisdiction}/codes/courts/{quote(court, safe='')}"
        category_review = fields.get("case category", {})
        type_review = fields.get("case type", {})
        filing_review = fields.get("filing type", {})

        categories = fetch(
            f"{root}/categories?{urlencode({'fileable_only': 'true', 'timing': 'Initial'})}"
        )
        category_names = accepted_names(category_review)
        category_matches = resolve_names(categories, category_names)
        checked += len(category_names)
        if category_names and len(category_matches) != len(category_names):
            failures.append(f"{case_id} case category: {category_names}")
        if not category_matches:
            continue

        case_types = fetch(
            f"{root}/case_types/?"
            + urlencode(
                {"category_id": category_matches[0]["code"], "timing": "Initial"}
            )
        )
        type_names = accepted_names(type_review)
        type_matches = resolve_names(case_types, type_names)
        checked += len(type_names)
        if type_names and len(type_matches) != len(type_names):
            failures.append(f"{case_id} case type: {type_names}")
        if not type_matches:
            continue

        filing_names = accepted_names(filing_review)
        if filing_names:
            filing_types = fetch(
                f"{root}/filing_types/?"
                + urlencode(
                    {
                        "initial": str(case_id not in SUBSEQUENT_CASES).lower(),
                        "category_id": category_matches[0]["code"],
                        "type_id": type_matches[0]["code"],
                    }
                )
            )
            filing_matches = resolve_names(filing_types, filing_names)
            checked += len(filing_names)
            if len(filing_matches) != len(filing_names):
                failures.append(f"{case_id} filing type: {filing_names}")

    if failures:
        print("Tyler label audit failures:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print(
        f"Verified {checked} durable Tyler names against {base_url}; numeric keys were not used as identity"
    )


if __name__ == "__main__":
    main()
