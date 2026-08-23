#!/usr/bin/env python3
"""Validate the form registry and optionally recheck Tyler labels by name.

Tyler's numeric taxonomy keys are environment-specific surrogate keys. This
audit uses them only transiently to walk the live hierarchy; a mapping is
identified by its category, case-type, and filing-type names.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

PROMPTFOO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CROSSWALK = PROMPTFOO_ROOT / "data" / "form_code_crosswalk.json"

CATALOG_STATUSES = {
    "observed_live",
    "current",
    "partially_current",
    "partial_observation",
    "not_current",
    "not_checked",
    "not_applicable",
}
ASSOCIATION_STATUSES = {
    "unverified_suggestion",
    "human_verified",
    "not_efileable",
    "not_applicable",
}


def normalized_name(value: Any) -> str:
    """Return the same conservative name normalization used at runtime."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).casefold()


def load_crosswalk(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        document = json.load(source)
    if not isinstance(document, dict) or not isinstance(document.get("registry"), list):
        raise ValueError("Crosswalk must be a JSON object containing a registry list")
    return document


def expected_summary(document: dict[str, Any]) -> dict[str, Any]:
    registry = document["registry"]
    mappings = [mapping for entry in registry for mapping in entry.get("mappings", [])]
    jurisdiction_counts = Counter(
        entry.get("form", {}).get("jurisdiction") for entry in registry
    )
    return {
        "total_forms": len(registry),
        "actual_forms": sum(
            entry.get("form", {}).get("is_form") is True for entry in registry
        ),
        "non_form_documents": sum(
            entry.get("form", {}).get("is_form") is False for entry in registry
        ),
        "forms_by_jurisdiction": {
            jurisdiction: jurisdiction_counts[jurisdiction]
            for jurisdiction in ("massachusetts", "vermont", "illinois")
        },
        "efileable_forms": sum(
            entry.get("form", {}).get("is_form") is True
            and entry.get("form", {}).get("is_efileable") is True
            for entry in registry
        ),
        "non_efileable_forms": sum(
            entry.get("form", {}).get("is_form") is True
            and entry.get("form", {}).get("is_efileable") is False
            for entry in registry
        ),
        "total_mappings": len(mappings),
        "complete_taxonomy_paths": sum(
            all(
                mapping.get(level) for level in ("category", "case_type", "filing_type")
            )
            for mapping in mappings
        ),
        "catalog_observed_mappings": sum(
            mapping.get("catalog_status")
            in {"observed_live", "current", "partially_current"}
            for mapping in mappings
        ),
        "catalog_current_mappings": sum(
            mapping.get("catalog_status") == "current" for mapping in mappings
        ),
        "catalog_partially_current_mappings": sum(
            mapping.get("catalog_status") == "partially_current" for mapping in mappings
        ),
        "catalog_partial_observations": sum(
            mapping.get("catalog_status") == "partial_observation"
            for mapping in mappings
        ),
        "catalog_not_current_mappings": sum(
            mapping.get("catalog_status") == "not_current" for mapping in mappings
        ),
        "human_verified_mappings": sum(
            mapping.get("association_status") == "human_verified"
            for mapping in mappings
        ),
        "unverified_suggestions": sum(
            mapping.get("association_status") == "unverified_suggestion"
            for mapping in mappings
        ),
        "not_efileable": sum(
            mapping.get("association_status") == "not_efileable" for mapping in mappings
        ),
        "not_applicable": sum(
            mapping.get("association_status") == "not_applicable"
            for mapping in mappings
        ),
    }


def structural_audit(document: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    canonical_ids: set[str] = set()
    mapping_keys: set[tuple[Any, ...]] = set()

    def add(kind: str, location: str, detail: str) -> None:
        issues.append({"kind": kind, "location": location, "detail": detail})

    for entry_index, entry in enumerate(document["registry"]):
        form = entry.get("form")
        location = f"registry[{entry_index}]"
        if not isinstance(form, dict):
            add("invalid_form", location, "form must be an object")
            continue
        canonical_id = str(form.get("canonical_id") or "")
        form_location = canonical_id or location
        if not canonical_id:
            add("missing_field", form_location, "form.canonical_id")
        elif canonical_id in canonical_ids:
            add("duplicate_canonical_id", form_location, canonical_id)
        canonical_ids.add(canonical_id)

        for field in (
            "jurisdiction",
            "canonical_name",
            "official",
            "source_urls",
            "is_efileable",
            "is_form",
        ):
            if field not in form:
                add("missing_field", form_location, f"form.{field}")
        if "source_url" in form:
            add(
                "legacy_field",
                form_location,
                "use form.source_urls list, not form.source_url",
            )
        if not isinstance(form.get("source_urls"), list):
            add("invalid_field", form_location, "form.source_urls must be a list")
        if form.get("is_form") is False and form.get("is_efileable") is True:
            add(
                "inconsistent_form_flags",
                form_location,
                "a non-form document cannot itself be e-fileable",
            )

        mappings = entry.get("mappings")
        if not isinstance(mappings, list):
            add("invalid_mappings", form_location, "mappings must be a list")
            continue
        for mapping_index, mapping in enumerate(mappings):
            mapping_location = f"{form_location}.mappings[{mapping_index}]"
            if not isinstance(mapping, dict):
                add("invalid_mapping", mapping_location, "mapping must be an object")
                continue
            for field in (
                "court_scope",
                "filing_phase",
                "confidence",
                "catalog_status",
                "association_status",
                "human_verification",
            ):
                if field not in mapping:
                    add("missing_field", mapping_location, f"mapping.{field}")
            if "review_status" in mapping or "reviewed_at" in mapping:
                add(
                    "legacy_field",
                    mapping_location,
                    "use catalog_status and association_status",
                )
            if mapping.get("catalog_status") not in CATALOG_STATUSES:
                add(
                    "invalid_catalog_status",
                    mapping_location,
                    repr(mapping.get("catalog_status")),
                )
            if mapping.get("association_status") not in ASSOCIATION_STATUSES:
                add(
                    "invalid_association_status",
                    mapping_location,
                    repr(mapping.get("association_status")),
                )
            confidence = mapping.get("confidence")
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                add("invalid_confidence", mapping_location, repr(confidence))

            verification = mapping.get("human_verification")
            if not isinstance(verification, dict):
                add("invalid_human_verification", mapping_location, "must be an object")
            else:
                verified = verification.get("verified") is True
                has_provenance = bool(
                    verification.get("verified_by") and verification.get("verified_at")
                )
                if verified != (mapping.get("association_status") == "human_verified"):
                    add(
                        "verification_status_mismatch",
                        mapping_location,
                        "human_verification.verified and association_status disagree",
                    )
                if verified and not has_provenance:
                    add(
                        "missing_verification_provenance",
                        mapping_location,
                        "reviewer and date are required",
                    )

            for level in ("category", "case_type", "filing_type"):
                value = mapping.get(level)
                if isinstance(value, str) and value != value.strip():
                    add(
                        "taxonomy_whitespace",
                        mapping_location,
                        f"{level} has outer whitespace: {value!r}",
                    )

            court_scope = mapping.get("court_scope") or {}
            court_names = (
                court_scope.get("court_names")
                if isinstance(court_scope, dict)
                else None
            )
            route_keys = (
                court_scope.get("observed_route_keys")
                if isinstance(court_scope, dict)
                else None
            )
            inactive_or_unscoped = (
                mapping.get("association_status") in {"not_efileable", "not_applicable"}
                or mapping.get("catalog_status") != "observed_live"
            )
            if not isinstance(court_names, list) or (
                not court_names and not inactive_or_unscoped
            ):
                add(
                    "invalid_court_scope",
                    mapping_location,
                    "court_names must be a non-empty list",
                )
                court_names = []
            if not isinstance(route_keys, list) or len(route_keys) != len(court_names):
                add(
                    "invalid_court_scope",
                    mapping_location,
                    "observed_route_keys must parallel court_names",
                )
            mapping_key = (
                canonical_id,
                tuple(normalized_name(value) for value in court_names),
                mapping.get("filing_phase"),
                *(
                    normalized_name(mapping.get(level))
                    for level in ("category", "case_type", "filing_type")
                ),
            )
            if mapping_key in mapping_keys:
                add(
                    "duplicate_mapping",
                    mapping_location,
                    "duplicate form, scope, phase, and taxonomy path",
                )
            mapping_keys.add(mapping_key)

            if mapping.get("catalog_status") in {
                "observed_live",
                "current",
                "partially_current",
            } and not mapping.get("filing_type"):
                add(
                    "incomplete_catalog_observation",
                    mapping_location,
                    "observed mapping has no filing type",
                )
            if (
                form.get("is_form") is False
                and mapping.get("association_status") != "not_applicable"
            ):
                add(
                    "non_form_mapping",
                    mapping_location,
                    "non-form documents must not recommend taxonomy paths",
                )
            if form.get("is_efileable") is False and mapping.get(
                "association_status"
            ) not in {
                "not_efileable",
                "not_applicable",
            }:
                add(
                    "paper_form_mapping",
                    mapping_location,
                    "non-efileable forms must not recommend taxonomy paths",
                )

    summary = document.get("summary")
    calculated = expected_summary(document)
    if summary != calculated:
        add(
            "summary_mismatch",
            "summary",
            f"expected {json.dumps(calculated, ensure_ascii=False, sort_keys=True)}",
        )
    return issues


@dataclass(frozen=True)
class LiveCheck:
    canonical_id: str
    mapping_index: int
    jurisdiction: str
    court_name: str
    observed_route_key: str
    filing_phase: str
    category: str
    case_type: str
    filing_type: str


class TylerClient:
    def __init__(self, endpoint: str, timeout: int = 30):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    @lru_cache(maxsize=None)
    def fetch(self, url: str) -> tuple[dict[str, Any], ...]:
        with urlopen(url, timeout=self.timeout) as response:  # noqa: S310 - endpoint comes from reviewed data
            value = json.load(response)
        if not isinstance(value, list):
            raise ValueError(f"Expected a list from {url}")
        return tuple(item for item in value if isinstance(item, dict))

    @lru_cache(maxsize=None)
    def court_route_key(self, jurisdiction: str, court_name: str) -> str | None:
        url = (
            f"{self.endpoint}/jurisdictions/{jurisdiction}/codes/courts/"
            f"?{urlencode({'fileable_only': 'true', 'with_names': 'true'})}"
        )
        court = self.resolve(self.fetch(url), court_name)
        return str(court.get("code")) if court else None

    def root(self, check: LiveCheck) -> str | None:
        current_route_key = self.court_route_key(check.jurisdiction, check.court_name)
        if current_route_key is None:
            return None
        court = quote(current_route_key, safe="")
        return (
            f"{self.endpoint}/jurisdictions/{check.jurisdiction}/codes/courts/{court}"
        )

    @staticmethod
    def resolve(
        items: tuple[dict[str, Any], ...], wanted: str
    ) -> dict[str, Any] | None:
        matches = [
            item
            for item in items
            if normalized_name(item.get("name")) == normalized_name(wanted)
        ]
        # Some Tyler environments publish the same stable label more than once
        # under different surrogate keys. Either key reaches the same named
        # child list, and no key is persisted by this audit.
        return matches[0] if matches else None

    def check(self, item: LiveCheck) -> dict[str, Any]:
        root = self.root(item)
        if root is None:
            return {"status": "missing", "level": "court", "expected": item.court_name}
        categories = self.fetch(
            f"{root}/categories?{urlencode({'fileable_only': 'true', 'timing': 'Initial'})}"
        )
        category = self.resolve(categories, item.category)
        if category is None:
            return {"status": "missing", "level": "category", "expected": item.category}

        case_types = self.fetch(
            f"{root}/case_types/?{urlencode({'category_id': category['code'], 'timing': 'Initial'})}"
        )
        case_type = self.resolve(case_types, item.case_type)
        if case_type is None:
            return {
                "status": "missing",
                "level": "case_type",
                "expected": item.case_type,
            }

        filing_types = self.fetch(
            f"{root}/filing_types/?"
            + urlencode(
                {
                    "initial": str(item.filing_phase == "initial").lower(),
                    "category_id": category["code"],
                    "type_id": case_type["code"],
                }
            )
        )
        filing_type = self.resolve(filing_types, item.filing_type)
        if filing_type is None:
            return {
                "status": "missing",
                "level": "filing_type",
                "expected": item.filing_type,
            }
        return {"status": "current"}


def live_checks(
    document: dict[str, Any], include_suggestions: bool
) -> tuple[list[LiveCheck], list[dict[str, str]]]:
    checks: list[LiveCheck] = []
    skipped: list[dict[str, str]] = []
    for entry in document["registry"]:
        form = entry["form"]
        for mapping_index, mapping in enumerate(entry.get("mappings", [])):
            if mapping.get("catalog_status") not in {
                "observed_live",
                "current",
                "partially_current",
                "partial_observation",
                "not_current",
            }:
                continue
            if (
                not include_suggestions
                and mapping.get("association_status") != "human_verified"
            ):
                continue
            location = f"{form['canonical_id']}.mappings[{mapping_index}]"
            if not all(
                mapping.get(level) for level in ("category", "case_type", "filing_type")
            ):
                skipped.append(
                    {
                        "location": location,
                        "reason": "incomplete taxonomy path cannot be checked hierarchically",
                    }
                )
                continue
            court_scope = mapping.get("court_scope", {})
            court_names = court_scope.get("court_names", [])
            observed_route_keys = court_scope.get("observed_route_keys", [])
            if not court_names:
                skipped.append({"location": location, "reason": "no live court scope"})
                continue
            for court_index, court_name in enumerate(court_names):
                checks.append(
                    LiveCheck(
                        canonical_id=form["canonical_id"],
                        mapping_index=mapping_index,
                        jurisdiction=form["jurisdiction"],
                        court_name=str(court_name),
                        observed_route_key=str(observed_route_keys[court_index]),
                        filing_phase=mapping["filing_phase"],
                        category=mapping["category"],
                        case_type=mapping["case_type"],
                        filing_type=mapping["filing_type"],
                    )
                )
    return checks, skipped


def run_live_audit(
    document: dict[str, Any], include_suggestions: bool
) -> dict[str, Any]:
    checks, skipped = live_checks(document, include_suggestions)
    client = TylerClient(document["endpoint"])
    results = []
    for index, check in enumerate(checks, start=1):
        try:
            outcome = client.check(check)
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            outcome = {"status": "error", "detail": f"{type(error).__name__}: {error}"}
        results.append(
            {
                "canonical_id": check.canonical_id,
                "mapping_index": check.mapping_index,
                "jurisdiction": check.jurisdiction,
                "court_name": check.court_name,
                "filing_phase": check.filing_phase,
                "taxonomy_path": {
                    "category": check.category,
                    "case_type": check.case_type,
                    "filing_type": check.filing_type,
                },
                **outcome,
            }
        )
        if index % 100 == 0:
            print(f"Checked {index}/{len(checks)} live taxonomy paths", file=sys.stderr)
    counts = Counter(result["status"] for result in results)
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "endpoint": document["endpoint"],
        "identity_policy": (
            "Taxonomy names are durable identifiers. Numeric keys returned by the endpoint were used only "
            "transiently to traverse the hierarchy and are intentionally absent from this report."
        ),
        "scope": "all observed candidate paths"
        if include_suggestions
        else "human-verified paths only",
        "summary": {
            "checks": len(results),
            "current": counts["current"],
            "missing": counts["missing"],
            "errors": counts["error"],
            "skipped_incomplete_or_unscoped": len(skipped),
        },
        "failures": [result for result in results if result["status"] != "current"],
        "results": results,
        "skipped": skipped,
    }


def apply_live_results(document: dict[str, Any], live_report: dict[str, Any]) -> None:
    """Record current name-based hierarchy results without persisting transient keys."""

    entries = {entry["form"]["canonical_id"]: entry for entry in document["registry"]}
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for result in live_report["results"]:
        grouped.setdefault(
            (result["canonical_id"], result["mapping_index"]), []
        ).append(result)

    checked_date = live_report["checked_at"][:10]
    for (canonical_id, mapping_index), results in grouped.items():
        mapping = entries[canonical_id]["mappings"][mapping_index]
        current_courts = [
            result["court_name"] for result in results if result["status"] == "current"
        ]
        failures = [result for result in results if result["status"] != "current"]
        if not failures:
            status = "current"
        elif current_courts:
            status = "partially_current"
        else:
            status = "not_current"
        mapping["catalog_status"] = status
        mapping["catalog_checked_at"] = checked_date
        mapping["catalog_validation"] = {
            "method": "exact normalized taxonomy-name hierarchy lookup",
            "current_court_names": current_courts,
            "failures": [
                {
                    "court_name": result["court_name"],
                    "level": result.get("level"),
                    "expected": result.get("expected"),
                }
                for result in failures
            ],
        }

    for entry in document["registry"]:
        for mapping in entry.get("mappings", []):
            if mapping.get("catalog_status") == "observed_live" and not all(
                mapping.get(level) for level in ("category", "case_type", "filing_type")
            ):
                mapping["catalog_status"] = "partial_observation"
    document["summary"] = expected_summary(document)


def safe_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit(
        (parts.scheme, parts.netloc, quote(parts.path), parts.query, parts.fragment)
    )


def run_source_audit(document: dict[str, Any]) -> dict[str, Any]:
    """Check each unique nonempty official source URL without downloading the file."""

    sources: dict[str, list[str]] = {}
    missing = []
    for entry in document["registry"]:
        form = entry["form"]
        urls = form.get("source_urls", [])
        if not urls:
            missing.append(form["canonical_id"])
        for url in urls:
            sources.setdefault(url, []).append(form["canonical_id"])

    def check(item: tuple[str, list[str]]) -> dict[str, Any]:
        url, canonical_ids = item
        try:
            request = Request(
                safe_url(url),
                headers={
                    "Range": "bytes=0-0",
                    "User-Agent": "LITEFile-crosswalk-audit/1.0",
                },
            )
            with urlopen(request, timeout=30) as response:  # noqa: S310 - reviewed registry URLs
                response.read(1)
                return {
                    "url": url,
                    "canonical_ids": canonical_ids,
                    "status": "reachable",
                    "http_status": response.status,
                    "content_type": response.headers.get_content_type(),
                    "final_url": response.geturl(),
                }
        except HTTPError as error:
            return {
                "url": url,
                "canonical_ids": canonical_ids,
                "status": "http_error",
                "http_status": error.code,
            }
        except (URLError, TimeoutError, ValueError) as error:
            return {
                "url": url,
                "canonical_ids": canonical_ids,
                "status": "error",
                "detail": f"{type(error).__name__}: {error}",
            }

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(check, sources.items()))
    counts = Counter(result["status"] for result in results)
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "summary": {
            "forms": len(document["registry"]),
            "forms_without_source_url": len(missing),
            "unique_urls": len(results),
            "reachable": counts["reachable"],
            "http_errors": counts["http_error"],
            "other_errors": counts["error"],
        },
        "forms_without_source_url": missing,
        "failures": [result for result in results if result["status"] != "reachable"],
        "results": results,
    }


def apply_source_results(
    document: dict[str, Any], source_report: dict[str, Any]
) -> None:
    results_by_url = {result["url"]: result for result in source_report["results"]}
    checked_date = source_report["checked_at"][:10]
    for entry in document["registry"]:
        form = entry["form"]
        urls = form.get("source_urls", [])
        statuses = [results_by_url[url]["status"] for url in urls]
        if not statuses:
            status = "missing"
        elif all(value == "reachable" for value in statuses):
            status = "current"
        elif any(value == "reachable" for value in statuses):
            status = "partially_current"
        else:
            status = "not_current"
        form["source_verification"] = {
            "status": status,
            "checked_at": checked_date,
            "reachable_urls": [
                url for url in urls if results_by_url[url]["status"] == "reachable"
            ],
            "unreachable_urls": [
                url for url in urls if results_by_url[url]["status"] != "reachable"
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Recheck complete mappings against the endpoint",
    )
    parser.add_argument(
        "--sources", action="store_true", help="Check official form source URLs"
    )
    parser.add_argument(
        "--include-suggestions",
        action="store_true",
        help="With --live, check unreviewed observed candidates as well as human-verified mappings",
    )
    parser.add_argument("--output", type=Path, help="Write a JSON audit report")
    parser.add_argument(
        "--update-crosswalk",
        action="store_true",
        help="Record live name-based validation statuses in the crosswalk; requires --live",
    )
    args = parser.parse_args()
    if args.update_crosswalk and not (args.live or args.sources):
        parser.error("--update-crosswalk requires --live or --sources")

    document = load_crosswalk(args.crosswalk)
    structural_issues = structural_audit(document)
    report: dict[str, Any] = {
        "audited_at": datetime.now(UTC).isoformat(),
        "crosswalk": str(args.crosswalk),
        "schema_version": document.get("schema_version"),
        "structural_summary": {"issues": len(structural_issues)},
        "structural_issues": structural_issues,
    }
    if args.live:
        report["live_audit"] = run_live_audit(document, args.include_suggestions)
        if args.update_crosswalk:
            apply_live_results(document, report["live_audit"])
            args.crosswalk.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            structural_issues = structural_audit(document)
            report["structural_summary"] = {"issues": len(structural_issues)}
            report["structural_issues"] = structural_issues
    if args.sources:
        report["source_audit"] = run_source_audit(document)
        if args.update_crosswalk:
            apply_source_results(document, report["source_audit"])
            args.crosswalk.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"Structural issues: {len(structural_issues)}")
    if args.live:
        live_summary = report["live_audit"]["summary"]
        print(
            "Live checks: "
            + ", ".join(f"{key}={value}" for key, value in live_summary.items())
        )
    if args.sources:
        source_summary = report["source_audit"]["summary"]
        print(
            "Source checks: "
            + ", ".join(f"{key}={value}" for key, value in source_summary.items())
        )
    failed_live = args.live and report["live_audit"]["summary"]["errors"]
    failed_sources = args.sources and report["source_audit"]["summary"]["other_errors"]
    if structural_issues or failed_live or failed_sources:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
