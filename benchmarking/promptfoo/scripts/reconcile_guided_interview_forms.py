#!/usr/bin/env python3
"""Reconcile source-identified interview PDFs without inventing filing paths.

Printed IDs identify forms. Exact provider label observations remain partial,
unverified suggestions; generic labels and composite bundles get no new mapping.
Run with --apply to update both registry copies after reviewing the manifests.
"""

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "efile_app/efile/data"
GENERIC_LABELS = {
    "motion",
    "order",
    "notice",
    "petition",
    "complaint",
    "answer",
    "summons",
    "affidavit",
    "exhibit",
    "additional information",
}


def name(value):
    return " ".join(
        re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", value or "").lower())
    )


def identifier(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def court_limited_source(doc):
    """Return true when the source identifies a Cook-only guided form."""
    form_id = doc.get("form_id") or ""
    urls = " ".join(doc.get("source_urls", [])).lower()
    repo_and_paths = (
        doc.get("repo", "") + " " + " ".join(doc.get("template_paths", []))
    ).lower()
    return (
        form_id.strip().upper().startswith("CCDR ")
        or "cook-county" in urls
        or "cook" in repo_and_paths
    )


def has_explicit_cook_scope(route_keys):
    return bool(route_keys) and all(route.startswith("cook:") for route in route_keys)


def search_aliases(manifests, label_index, checked_at):
    """Translate printed Illinois IDs only where a precise source title agrees.

    These aliases search existing paths; they never supply a provider code.
    Vermont's workbook associations are separately curated in the main YAML.
    Court-specific templates and ambiguous fragments require manual review.
    """
    result = {
        "version": 1,
        "checked_at": checked_at,
        "concepts": {},
        "definitions": {},
        "path_aliases": [],
    }
    for manifest in manifests:
        if manifest["state"] != "illinois":
            continue
        labels = {
            name(label): stages
            for label, stages in label_index.get("illinois", {}).items()
        }
        for doc in manifest["documents"]:
            form_id = doc.get("form_id")
            title = doc.get("printed_title") or doc["title"]
            if (
                doc["filing_status"] != "court_filing"
                or doc.get("output_kind", "document") != "document"
                or "bundle_components" in doc
                or not form_id
                or not doc.get("printed_title")
                or name(title) in GENERIC_LABELS
                or doc["stage"] == "unknown"
                or court_limited_source(doc)
                or "appeal" in doc["repo"].lower()
            ):
                continue
            stages = labels.get(name(title), {})
            key = "guided_il_" + identifier(form_id)
            for stage, observed in stages.items():
                if doc["stage"] not in {stage, "both"} or not observed:
                    continue
                result["concepts"][key] = {
                    "path_only": True,
                    "jurisdictions": ["illinois"],
                    "terms": [form_id],
                }
                result["definitions"][key] = {
                    "label": f"Form {form_id}",
                    "default": {
                        "text": f"Form {form_id}: {observed[0]['label']}. Available filing options depend on your court and case.",
                        "source": doc["source_urls"][0],
                    },
                }
                rule = {
                    "jurisdictions": ["illinois"],
                    "initial": stage == "initial",
                    "filing_type": [observed[0]["label"]],
                    "concepts": [key],
                    "source_output": doc["id"],
                    "source_urls": doc["source_urls"],
                    "evidence_status": "source_title_and_provider_label; selected_path_not_audited",
                }
                if doc.get("case_categories"):
                    rule["case_category"] = doc["case_categories"]
                # Interview case-family names are not necessarily provider
                # case-type labels (e.g. "Parenting Responsibilities"). The
                # specific filing label and division provide the source scope;
                # never turn a conceptual family into an exact path constraint.
                if rule not in result["path_aliases"]:
                    result["path_aliases"].append(rule)
    return result


def add_reviewed_search_aliases(aliases, evidence):
    """Share reviewed Illinois associations with Find code, preserving local scope."""
    if evidence["state"] != "illinois":
        return
    for record in evidence["records"]:
        if record.get("mapping_status") != "verified_label" or not record.get(
            "exact_filing_type"
        ):
            continue
        if any(
            form_id.strip().upper().startswith("CCDR ")
            for form_id in record["form_ids"]
        ) and not has_explicit_cook_scope(record.get("court_codes", [])):
            continue
        phase = record.get("stage_constraint", "")
        stages = record.get("available_stages", [])
        if phase.startswith("subsequent"):
            stages = [stage for stage in stages if stage == "subsequent"]
        elif phase.startswith("initial"):
            stages = [stage for stage in stages if stage == "initial"]
        for form_id in record["form_ids"]:
            key = "guided_il_" + identifier(form_id)
            aliases["concepts"][key] = {
                "path_only": True,
                "jurisdictions": ["illinois"],
                "terms": [form_id],
            }
            aliases["definitions"][key] = {
                "label": f"Form {form_id}",
                "default": {
                    "text": f"Form {form_id}: {record['source_document_title']}. Filing labels vary by court; choose the option for your court and case.",
                    "source": record["source_urls"][0],
                },
            }
            for stage in stages:
                rule = {
                    "jurisdictions": ["illinois"],
                    "initial": stage == "initial",
                    "filing_type": [record["exact_filing_type"]],
                    "concepts": [key],
                    "source_urls": record["source_urls"],
                    "evidence_status": "reviewed_source_association",
                }
                if record.get("case_category"):
                    rule["case_category"] = [record["case_category"]]
                if record.get("court_codes"):
                    rule["court_codes"] = record["court_codes"]
                if record.get("search_terms"):
                    rule["terms"] = record["search_terms"]
                if rule not in aliases["path_aliases"]:
                    aliases["path_aliases"].append(rule)


def reconcile(registry, manifests, label_index, checked_at):
    changes = []
    id_index, title_index = defaultdict(list), defaultdict(list)
    work = []
    statewide_sources = set()
    court_limited_output_ids = set()

    for manifest in manifests:
        state = manifest["state"]
        labels = {
            name(label): stages for label, stages in label_index.get(state, {}).items()
        }
        for doc in manifest["documents"]:
            if (
                doc["filing_status"] != "court_filing"
                or doc.get("output_kind", "document") != "document"
                or "bundle_components" in doc
            ):
                continue
            title = doc.get("printed_title") or doc["title"]
            form_id = doc.get("form_id")
            if form_id and title:
                source_key = (state, identifier(form_id), name(title))
                if court_limited_source(doc):
                    court_limited_output_ids.add(doc["id"])
                else:
                    statewide_sources.add(source_key)
            work.append((state, doc, labels))

    # Process the strongest source first, independent of manifest order. A
    # later Cook-only twin must not erase a mapping independently supported by
    # a non-Cook source with the same printed identity/title.
    work.sort(key=lambda row: (row[0], court_limited_source(row[1]), row[1]["id"]))

    def index(entry):
        form = entry["form"]
        state = form["jurisdiction"]
        for value in [form.get("form_id"), *form.get("form_id_aliases", [])]:
            if value:
                if entry not in id_index[state, identifier(value)]:
                    id_index[state, identifier(value)].append(entry)
        for value in [form["canonical_name"], *form.get("aliases", [])]:
            if entry not in title_index[state, name(value)]:
                title_index[state, name(value)].append(entry)

    for entry in registry["registry"]:
        index(entry)
    for state, doc, labels in work:
        sources = [url for url in doc["source_urls"] if url.startswith("https://")]
        if not sources or not doc["template_paths"]:
            continue
        title = doc.get("printed_title") or doc["title"]
        form_id = doc.get("form_id")
        # A compound identifier or unresolved source expression is not a
        # printed form identity, even if a parser found something in it.
        if form_id and ("," in form_id or "${" in form_id):
            raise ValueError(f"{doc['id']}: ambiguous form identifier {form_id!r}")
        if "${" in title or not title.strip():
            continue
        matches = (
            id_index[state, identifier(form_id)]
            if form_id
            else title_index[state, name(title)]
        )
        if len(matches) > 1:
            changes.append(
                {"output": doc["id"], "status": "ambiguous_existing_identity"}
            )
            continue
        if matches:
            entry = matches[0]
        else:
            suffix = (
                identifier(form_id)
                if form_id
                else hashlib.sha256(
                    (
                        doc["repo"] + "|" + doc["template_paths"][0] + "|" + name(title)
                    ).encode()
                ).hexdigest()[:16]
            )
            entry = {
                "form": {
                    "canonical_id": {"vermont": "VT", "illinois": "IL"}[state]
                    + "-GUIDED-"
                    + suffix,
                    "jurisdiction": state,
                    "form_id": form_id,
                    "canonical_name": title,
                    "aliases": [],
                    "official": False,
                    "is_form": True,
                    "is_efileable": None,
                    "document_role": "court_form",
                    "source_urls": sources,
                    "source_verification": {
                        "status": "current",
                        "checked_at": checked_at,
                        "reachable_urls": sources,
                        "unreachable_urls": [],
                    },
                    "description": "Court document generated by a partner interview. Source identity is recorded from the pinned template; official-form approval and filing eligibility are not inferred from repository publication.",
                },
                "mappings": [],
            }
            registry["registry"].append(entry)
            index(entry)
            changes.append(
                {
                    "output": doc["id"],
                    "status": "added_source_identity",
                    "canonical_id": entry["form"]["canonical_id"],
                }
            )
        form = entry["form"]
        limited_source = court_limited_source(doc)
        if limited_source:
            # Remove the previous importer-generated, unscoped exact-title
            # suggestion if a later audit identifies this source as
            # court-limited. Preserve mappings with explicit Cook routes.
            source_key = (state, identifier(form_id), name(title))
            if source_key not in statewide_sources:
                old_count = len(entry["mappings"])
                entry["mappings"] = [
                    mapping
                    for mapping in entry["mappings"]
                    if not (
                        name(mapping.get("filing_type")) == name(title)
                        and doc["id"] in mapping.get("notes", "")
                        and not has_explicit_cook_scope(
                            mapping.get("court_scope", {}).get(
                                "observed_route_keys", []
                            )
                        )
                    )
                ]
                if len(entry["mappings"]) != old_count:
                    changes.append(
                        {
                            "output": doc["id"],
                            "status": "removed_unscoped_court_limited_mapping",
                        }
                    )
        alias_values = (title, doc["title"])
        for value in alias_values:
            if name(value) in GENERIC_LABELS and name(value) != name(title):
                continue
            if value != form["canonical_name"] and value not in form.setdefault(
                "aliases", []
            ):
                form["aliases"].append(value)
        for url in sources:
            if url not in form.setdefault("source_urls", []):
                form["source_urls"].append(url)
        if doc["id"] not in form.setdefault("guided_interview_outputs", []):
            form["guided_interview_outputs"].append(doc["id"])
        index(entry)
        # Only exact document-title / provider-label matches. Do not turn
        # inferred candidate labels into generic Motion/Order suggestions.
        if form.get("is_efileable") is False or form.get("is_form") is False:
            continue
        stages = labels.get(name(title), {})
        if not stages or name(title) in GENERIC_LABELS:
            continue
        wanted = (
            [doc["stage"]]
            if doc["stage"] in {"initial", "subsequent"}
            else list(stages)
        )
        observed = [row for stage in wanted for row in stages.get(stage, [])]
        if not observed:
            continue
        # A Cook County source page or CCDR form prefix is not evidence
        # that the same title maps to statewide filing paths.
        if limited_source:
            continue
        filing_label = observed[0]["label"]
        existing_mapping = next(
            (
                row
                for row in entry["mappings"]
                if name(row.get("filing_type")) == name(filing_label)
            ),
            None,
        )
        if existing_mapping:
            # If an older run attributed a shared mapping to the Cook
            # output, rewrite its provenance to this independently
            # supported non-Cook source once. The sorted pass makes that
            # choice stable on subsequent runs.
            if not limited_source and any(
                output_id in existing_mapping.get("notes", "")
                for output_id in court_limited_output_ids
            ):
                existing_mapping["notes"] = (
                    "Exact document title matches the observed provider label; "
                    "no complete category/case-type path is established. "
                    f"Source: {sources[0]}. Output: {doc['id']}."
                )
                changes.append(
                    {
                        "output": doc["id"],
                        "status": "updated_mapping_source_to_non_cook_output",
                        "canonical_id": form["canonical_id"],
                        "filing_type": filing_label,
                    }
                )
            continue
        entry["mappings"].append(
            {
                "court_scope": {
                    "court_names": [],
                    "observed_route_keys": [],
                    "note": "Exact label observed in provider court/stage option lists; no complete court/category/case-type path established.",
                },
                "filing_phase": doc["stage"]
                if doc["stage"] in {"initial", "subsequent"}
                else None,
                "category": None,
                "case_type": None,
                "filing_type": filing_label,
                "confidence": 0.5,
                "catalog_status": "partial_observation",
                "catalog_checked_at": checked_at,
                "association_status": "unverified_suggestion",
                "human_verification": {
                    "verified": False,
                    "verified_by": None,
                    "verified_at": None,
                    "notes": None,
                },
                "notes": f"Source template title exactly matches the observed provider label. This is an advisory label association, not a validated court path. Source: {sources[0]}. Output: {doc['id']}.",
            }
        )
        changes.append(
            {
                "output": doc["id"],
                "status": "added_exact_label_observation",
                "canonical_id": form["canonical_id"],
                "filing_type": filing_label,
            }
        )
    registry["updated_at"] = checked_at
    return changes


def apply_reviewed_associations(registry, evidence):
    """Replace broad historical guesses with individually reviewed associations.

    The supplied evidence distinguishes source meaning from provider label
    availability. These remain advisory, even when a selected path was checked.
    Initial Filing has a separate path audit and is left intact here.
    """
    corrections = {
        row["canonical_id"]: row
        for row in evidence.get("form_metadata_corrections", [])
    }
    for entry in registry["registry"]:
        form = entry["form"]
        correction = corrections.get(form["canonical_id"])
        if not correction or form["jurisdiction"] != evidence["state"]:
            continue
        if identifier(form.get("form_id")) != identifier(correction["form_id"]):
            raise ValueError(
                "Metadata correction identifier does not match its canonical form"
            )
        for key, value in correction["changes"].items():
            if key == "source_urls_add":
                form["source_urls"] = list(
                    dict.fromkeys([*form["source_urls"], *value])
                )
            elif key == "canonical_name":
                if form[key] != value and form[key] not in form.setdefault(
                    "aliases", []
                ):
                    form["aliases"].append(form[key])
                form[key] = value
            elif key in {
                "department",
                "description",
                "is_efileable",
                "source_verification",
            }:
                form[key] = value
            else:
                raise ValueError(f"Unsupported reviewed metadata correction: {key}")
        form["metadata_review_note"] = correction["reason"]
    by_id = defaultdict(list)
    for record in evidence["records"]:
        if (
            not record.get("exact_filing_type")
            or record["exact_filing_type"] == "Initial Filing"
        ):
            continue
        if record.get("mapping_status") != "verified_label":
            continue
        # CCDR identifies Cook County Domestic Relations forms. Without
        # observed Cook route keys, do not apply their labels statewide.
        if any(
            form_id.strip().upper().startswith("CCDR ")
            for form_id in record["form_ids"]
        ) and not has_explicit_cook_scope(record.get("court_codes", [])):
            continue
        for form_id in record["form_ids"]:
            by_id[identifier(form_id)].append(record)
    changes = []
    for entry in registry["registry"]:
        form = entry["form"]
        records = by_id.get(identifier(form.get("form_id")), [])
        if (
            form["jurisdiction"] != evidence["state"]
            or not records
            or form.get("is_efileable") is False
        ):
            continue
        # Keep the independently audited initial-filing associations while
        # replacing only other reviewed suggestions.
        mappings = [
            mapping
            for mapping in entry["mappings"]
            if mapping.get("filing_type") == "Initial Filing"
        ]
        for record in records:
            category = record.get("case_category")
            if category and "/" in category:
                category = None
            types = record.get("case_types", [])
            phase = next(
                (
                    stage
                    for stage in ("initial", "subsequent")
                    if record.get("stage_constraint", "").startswith(stage)
                ),
                None,
            )
            mapping = {
                "court_scope": {
                    "court_names": record.get("court_names", []),
                    "observed_route_keys": record.get("court_codes", []),
                    "note": "Source-specific association; court/stage label observations do not establish every selected case path.",
                },
                "category": category,
                "case_type": types[0]["name"] if len(types) == 1 else None,
                "filing_type": record["exact_filing_type"],
                "filing_phase": phase,
                "confidence": 0.7,
                "catalog_status": "partial_observation",
                "catalog_checked_at": evidence["checked_at"],
                "association_status": "unverified_suggestion",
                "human_verification": {
                    "verified": False,
                    "verified_by": None,
                    "verified_at": None,
                    "notes": None,
                },
                "notes": record["reason"],
                "source_urls": record["source_urls"],
            }
            if mapping not in mappings:
                mappings.append(mapping)
        if not evidence.get("replace_existing", True):
            mappings = entry["mappings"] + [
                mapping for mapping in mappings if mapping not in entry["mappings"]
            ]
        if entry["mappings"] != mappings:
            entry["mappings"] = mappings
            changes.append(
                {
                    "canonical_id": form["canonical_id"],
                    "status": "replaced_reviewed_associations",
                }
            )
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-index", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--reviewed-associations",
        type=Path,
        action="append",
        default=[],
        help="Reviewed form/label evidence; repeat for multiple files.",
    )
    args = parser.parse_args()
    inventory = json.loads((DATA / "guided_interview_inventory.json").read_text())
    manifests = [
        json.loads((DATA / path).read_text()) for path in inventory["manifest_files"]
    ]
    path = DATA / "form_code_crosswalk.json"
    registry = json.loads(path.read_text())
    changes = reconcile(
        registry,
        manifests,
        json.loads(args.label_index.read_text()),
        inventory["checked_at"],
    )
    for reviewed_path in args.reviewed_associations:
        changes.extend(
            apply_reviewed_associations(registry, json.loads(reviewed_path.read_text()))
        )
    args.report.write_text(json.dumps(changes, indent=2, ensure_ascii=False) + "\n")
    if args.apply:
        spec = importlib.util.spec_from_file_location(
            "crosswalk_audit", Path(__file__).with_name("audit_form_code_crosswalk.py")
        )
        assert spec and spec.loader
        audit = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = audit
        spec.loader.exec_module(audit)
        registry["summary"] = audit.expected_summary(registry)
        text = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text)
        (ROOT / "benchmarking/promptfoo/data/form_code_crosswalk.json").write_text(text)
        aliases = search_aliases(
            manifests, json.loads(args.label_index.read_text()), inventory["checked_at"]
        )
        for reviewed_path in args.reviewed_associations:
            add_reviewed_search_aliases(aliases, json.loads(reviewed_path.read_text()))
        (DATA / "guided_form_search_aliases.json").write_text(
            json.dumps(aliases, indent=2, ensure_ascii=False) + "\n"
        )
    print(
        f"{len(changes)} reconciliation actions; {'applied' if args.apply else 'preview only'}."
    )


if __name__ == "__main__":
    main()
