#!/usr/bin/env python3
"""Build Promptfoo JSONL cases from the synthetic corpus and label reviews."""

import argparse
import json
import re
from pathlib import Path

PROMPTFOO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PROMPTFOO_ROOT.parent
SYNTHETIC_ROOT = BENCHMARK_ROOT / "synthetic"
OUTPUT_PATH = PROMPTFOO_ROOT / "data" / "cases.jsonl"
SENTINEL_OUTPUT_PATH = PROMPTFOO_ROOT / "data" / "sentinel_cases.jsonl"
MODALITY_OUTPUT_PATH = PROMPTFOO_ROOT / "data" / "modality_cases.jsonl"
PRODUCTION_CONTEXT_OUTPUT_PATH = (
    PROMPTFOO_ROOT / "data" / "production_context_cases.jsonl"
)
REVIEW_PATH = PROMPTFOO_ROOT / "data" / "tyler_label_reviews.json"

SENTINEL_SPECS = [
    {
        "case_id": "MA-01",
        "variant": "interactive",
        "rationale": "Common initiating filing and the interactive half of a matched PDF pair.",
    },
    {
        "case_id": "MA-01",
        "variant": "flattened",
        "rationale": "Same facts as the interactive form, testing sensitivity to PDF structure.",
    },
    {
        "case_id": "VT-06",
        "variant": "flattened",
        "rationale": "Short name-change petition with a Tyler-verified classification.",
    },
    {
        "case_id": "IL-04",
        "variant": "flattened",
        "rationale": "Small-claims filing with a plausible but genuinely ambiguous Tyler case type.",
    },
    {
        "case_id": "IL-08",
        "variant": "flattened",
        "rationale": "Later fee-waiver form whose identity differs from the underlying Eviction category; case type remains unknown.",
    },
    {
        "case_id": "IL-10",
        "variant": "motion-facsimile",
        "rationale": "Generic motion whose caption and docket support limited underlying-case inference.",
    },
]

KEY_ALIASES = {
    "court name": "court",
    "court unit": "court",
    "court or county": "court",
    "case number": "docket number",
    "docker number": "docket number",
}


def normalized_key(key):
    key = str(key).strip().lower()
    return KEY_ALIASES.get(key, key)


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def add_target(expected, key, value, *, confidence, review_status, source):
    key = normalized_key(key)
    values = value if isinstance(value, list) else [value]
    target = expected.setdefault(
        key,
        {
            "accepted": [],
            "confidence": confidence,
            "review_status": review_status,
            "source": source,
        },
    )
    for candidate in values:
        if candidate not in target["accepted"]:
            target["accepted"].append(candidate)


def add_form_targets(case, expected):
    """Add exact printed form identity supplied by the synthetic source record."""
    form_name = case.get("form_name")
    form_number = case.get("form_number")
    if form_name:
        add_target(
            expected,
            "form name",
            form_name,
            confidence=0.99,
            review_status="synthetic_document_ground_truth",
            source="document",
        )
    if form_number:
        revision = re.search(r"(?<!\d)(\d{2}/\d{2,4})(?!\d)", form_number)
        identifier = form_number
        if revision:
            identifier = re.sub(
                r"(?:\s+-\s+|\s*\()" + re.escape(revision.group(1)) + r"\)?\s*$",
                "",
                form_number,
            ).strip()
        add_target(
            expected,
            "form identifier",
            identifier,
            confidence=0.99,
            review_status="synthetic_document_ground_truth",
            source="document",
        )
        if revision:
            add_target(
                expected,
                "form revision",
                revision.group(1),
                confidence=0.99,
                review_status="synthetic_document_ground_truth",
                source="document",
            )


def apply_reviews(case_id, expected, abstain, reviews):
    review_notes = []
    for raw_key, review in reviews.get(case_id, {}).items():
        key = normalized_key(raw_key)
        if review.get("required") is False:
            expected.pop(key, None)
        if review.get("abstain") and key not in abstain:
            abstain.append(key)
        if review.get("required", True) and review.get("accepted"):
            # Reviewed catalog names replace provisional semantic labels. Natural
            # document titles remain separate fields and are not lost here.
            expected[key] = {
                "accepted": list(dict.fromkeys(review["accepted"])),
                "confidence": review.get("confidence", 0.75),
                "review_status": review.get("review_status", "reviewed"),
                "source": "tyler_catalog",
            }
        if key in expected:
            target = expected[key]
            for metadata_key in (
                "confidence",
                "review_status",
                "preferred_name",
                "catalog_observations",
                "notes",
            ):
                if metadata_key in review:
                    target[metadata_key] = review[metadata_key]
        if review.get("notes"):
            review_notes.append(f"{key}: {review['notes']}")
    return review_notes


def expected_from_extractability(case, reviews):
    expected = {}
    add_form_targets(case, expected)
    for key, value in case.get("directly_visible_or_labeled", {}).items():
        add_target(
            expected,
            key,
            value,
            confidence=0.99,
            review_status="synthetic_document_ground_truth",
            source="document",
        )
    for key, value in case.get("semantic_but_reasonable", {}).items():
        add_target(
            expected,
            key,
            value,
            confidence=0.65,
            review_status="synthetic_semantic_label_unverified",
            source="semantic_inference",
        )
    abstain = [normalized_key(key) for key in case.get("do_not_require", [])]
    review_notes = apply_reviews(case["id"], expected, abstain, reviews)
    allowed = {
        normalized_key(key): value
        for key, value in case.get("optional_inferences", {}).items()
    }
    return expected, sorted(set(abstain)), allowed, review_notes


def expected_from_motion(case, reviews):
    expected = {}
    add_form_targets(case, expected)
    for key, value in case.get("expected_extraction", {}).items():
        source = (
            "document"
            if key not in {"case category", "case type", "filing type"}
            else "semantic_inference"
        )
        add_target(
            expected,
            key,
            value,
            confidence=0.99 if source == "document" else 0.65,
            review_status="synthetic_document_ground_truth"
            if source == "document"
            else "synthetic_semantic_label_unverified",
            source=source,
        )
    abstain = [normalized_key(key) for key in case.get("abstention_targets", [])]
    review_notes = apply_reviews(case["id"], expected, abstain, reviews)
    allowed = {
        normalized_key(key): value
        for key, value in case.get("allowed_inferences", {}).items()
    }
    return expected, sorted(set(abstain)), allowed, review_notes


def promptfoo_case(
    case, *, pdf_path, variant, expected, abstain, allowed, review_notes
):
    relative_pdf = Path(pdf_path).as_posix()
    return {
        "description": f"{case['id']} {variant}: {case['form_name']}",
        "vars": {
            "document": f"file://../synthetic/{relative_pdf}",
            "document_input_id": f"{case['id']}::{variant}",
            "jurisdiction": case["jurisdiction"],
            "expected": expected,
            "abstain": abstain,
            "allowed_inferences": allowed,
        },
        "metadata": {
            "case_id": case["id"],
            "variant": variant,
            "jurisdiction": case["jurisdiction"],
            "form_name": case["form_name"],
            "synthetic": True,
            "label_review_notes": review_notes,
        },
    }


def build_cases():
    review_document = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    reviews = review_document["cases"]
    cases = []
    for case in read_jsonl(SYNTHETIC_ROOT / "extractability.jsonl"):
        expected, abstain, allowed, review_notes = expected_from_extractability(
            case, reviews
        )
        for variant in ("interactive", "flattened"):
            cases.append(
                promptfoo_case(
                    case,
                    pdf_path=case[f"{variant}_pdf"],
                    variant=variant,
                    expected=expected,
                    abstain=abstain,
                    allowed=allowed,
                    review_notes=review_notes,
                )
            )
    for case in read_jsonl(SYNTHETIC_ROOT / "motion_cases.jsonl"):
        expected, abstain, allowed, review_notes = expected_from_motion(case, reviews)
        cases.append(
            promptfoo_case(
                case,
                pdf_path=case["synthetic_pdf"],
                variant="motion-facsimile",
                expected=expected,
                abstain=abstain,
                allowed=allowed,
                review_notes=review_notes,
            )
        )
    return cases


def render_jsonl(cases):
    return "".join(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n"
        for case in cases
    )


def build_sentinel_cases(cases):
    indexed = {
        (case["metadata"]["case_id"], case["metadata"]["variant"]): case
        for case in cases
    }
    sentinel_cases = []
    for spec in SENTINEL_SPECS:
        source = indexed[(spec["case_id"], spec["variant"])]
        sentinel = json.loads(json.dumps(source))
        slug = f"{spec['case_id'].lower()}-{spec['variant']}"
        sentinel["vars"]["document_image"] = (
            f"file://./.generated/sentinel_images/{slug}.png"
        )
        sentinel["metadata"]["sentinel_rationale"] = spec["rationale"]
        sentinel["metadata"]["source_document"] = source["vars"]["document"]
        sentinel_cases.append(sentinel)

    # A raster-only PDF makes the modality test diagnostic: text extraction should
    # have no useful document text while vision sees the same MA-01 page.
    scan = json.loads(json.dumps(indexed[("MA-01", "flattened")]))
    scan["description"] = "MA-01 scanned: Complaint for Divorce under G.L. c. 208, § 1B"
    scan["vars"]["document"] = (
        "file://./.generated/sentinel_documents/ma-01-scanned.pdf"
    )
    scan["vars"]["document_input_id"] = "MA-01::scanned"
    scan["vars"]["document_image"] = (
        "file://./.generated/sentinel_images/ma-01-scanned.png"
    )
    scan["metadata"]["variant"] = "scanned"
    scan["metadata"]["source_variant"] = "flattened"
    scan["metadata"]["source_document"] = indexed[("MA-01", "flattened")]["vars"][
        "document"
    ]
    scan["metadata"]["sentinel_rationale"] = (
        "Raster-only scan of MA-01: expected to separate text fallback from page vision."
    )
    sentinel_cases.append(scan)
    return sentinel_cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Fail if cases.jsonl is not up to date"
    )
    args = parser.parse_args()
    cases = build_cases()
    rendered = render_jsonl(cases)
    sentinel_cases = build_sentinel_cases(cases)
    sentinel_rendered = render_jsonl(sentinel_cases)
    modality_rendered = render_jsonl(
        [
            case
            for case in sentinel_cases
            if case["metadata"]["case_id"] == "MA-01"
            and case["metadata"]["variant"] in {"flattened", "scanned"}
        ]
    )
    production_context_rendered = render_jsonl(
        [
            case
            for case in sentinel_cases
            if case["metadata"]["case_id"] == "MA-01"
            and case["metadata"]["variant"] in {"interactive", "flattened", "scanned"}
        ]
    )
    if args.check:
        existing = (
            OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        )
        sentinel_existing = (
            SENTINEL_OUTPUT_PATH.read_text(encoding="utf-8")
            if SENTINEL_OUTPUT_PATH.exists()
            else ""
        )
        modality_existing = (
            MODALITY_OUTPUT_PATH.read_text(encoding="utf-8")
            if MODALITY_OUTPUT_PATH.exists()
            else ""
        )
        production_context_existing = (
            PRODUCTION_CONTEXT_OUTPUT_PATH.read_text(encoding="utf-8")
            if PRODUCTION_CONTEXT_OUTPUT_PATH.exists()
            else ""
        )
        if (
            existing != rendered
            or sentinel_existing != sentinel_rendered
            or modality_existing != modality_rendered
            or production_context_existing != production_context_rendered
        ):
            raise SystemExit(
                "promptfoo/data/cases.jsonl is out of date; run npm run build-cases"
            )
        return
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    SENTINEL_OUTPUT_PATH.write_text(sentinel_rendered, encoding="utf-8")
    MODALITY_OUTPUT_PATH.write_text(modality_rendered, encoding="utf-8")
    PRODUCTION_CONTEXT_OUTPUT_PATH.write_text(
        production_context_rendered, encoding="utf-8"
    )
    print(f"Wrote {len(rendered.splitlines())} cases to {OUTPUT_PATH}")
    print(
        f"Wrote {len(sentinel_rendered.splitlines())} cases to {SENTINEL_OUTPUT_PATH}"
    )
    print(
        f"Wrote {len(modality_rendered.splitlines())} cases to {MODALITY_OUTPUT_PATH}"
    )
    print(
        f"Wrote {len(production_context_rendered.splitlines())} cases "
        f"to {PRODUCTION_CONTEXT_OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
