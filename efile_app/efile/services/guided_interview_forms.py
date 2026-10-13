"""Source inventory for generated interview documents, separate from code availability.

A reviewed repository, a generated PDF, a published interview, an identified
form, and a selectable filing path are different facts. This report keeps them
separate so source inventory coverage cannot masquerade as court coverage.
"""

import json
import re
from collections import Counter
from pathlib import Path

from efile.services.taxonomy_classification import deterministic_form_identity, exact_form_crosswalk_matches

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_inventory(directory=DATA_DIR):
    directory = Path(directory)
    inventory = json.loads((directory / "guided_interview_inventory.json").read_text())
    manifests = [json.loads((directory / name).read_text()) for name in inventory["manifest_files"]]
    return inventory, manifests


def inventory_errors(inventory, manifests):
    """Reject missing repositories, untraceable outputs, and contradictory claims."""
    errors = []
    expected = {row["repo"]: row["state"] for row in inventory["repositories"]}
    seen_repositories = Counter()
    seen_documents = Counter()
    for manifest in manifests:
        state = manifest["state"]
        repositories = {row["repo"]: row for row in manifest["repositories"]}
        seen_repositories.update(row["repo"] for row in manifest["repositories"])
        for repo, record in repositories.items():
            if expected.get(repo) != state:
                errors.append(f"{repo}: unexpected repository or wrong state")
            if not record.get("commit") or not record.get("source_url") or not record.get("reason"):
                errors.append(f"{repo}: missing source revision, URL, or review disposition")
        for document in manifest["documents"]:
            identity = document["id"]
            seen_documents.update([identity])
            repo = document["repo"]
            if repo not in repositories:
                errors.append(f"{identity}: repository has no review record")
            source_urls = document.get("source_urls")
            template_paths = document.get("template_paths")
            has_static_template = isinstance(template_paths, list) and bool(template_paths)
            # Some interviews construct attachment PDFs inline or as a bundle,
            # so there is no standalone template file to list. The attachment
            # variable and source URL still tie that output to the inspected
            # source. Bundles also identify their components where available.
            has_explicit_source_output = bool(
                document.get("entrypoint")
                and document.get("attachment_variable")
                and isinstance(source_urls, list)
                and source_urls
            )
            if (
                not document.get("entrypoint")
                or not source_urls
                or not (has_static_template or has_explicit_source_output)
            ):
                errors.append(f"{identity}: output has no entrypoint/source evidence")
            if not document.get("title") or not document.get("publication_status"):
                errors.append(f"{identity}: missing document title or publication disposition")
            if document.get("stage") not in {"initial", "subsequent", "both", "unknown"}:
                errors.append(f"{identity}: invalid filing stage")
            if document.get("filing_status") not in {"court_filing", "noncourt", "uncertain"}:
                errors.append(f"{identity}: invalid filing disposition")
            if document.get("output_kind", "document") not in {"document", "bundle", "fragment"}:
                errors.append(f"{identity}: invalid output kind")
            if document.get("filing_status") == "noncourt":
                if not document.get("exclusion_reason"):
                    errors.append(f"{identity}: excluded without a reason")
                if document.get("filing_type_labels"):
                    errors.append(f"{identity}: excluded document still suggests filing codes")
            if document.get("mapping_status") == "verified_label" and not document.get("mapping_evidence"):
                errors.append(f"{identity}: label verification has no evidence")
    errors.extend(f"{repo}: missing repository review" for repo in sorted(set(expected) - set(seen_repositories)))
    errors.extend(f"{repo}: duplicate repository review" for repo, count in seen_repositories.items() if count > 1)
    errors.extend(f"{doc}: duplicate output identity" for doc, count in seen_documents.items() if count > 1)
    return errors


def inventory_report(inventory, manifests):
    errors = inventory_errors(inventory, manifests)
    states = {}
    documents = []
    for manifest in manifests:
        state = manifest["state"]
        counts = states.setdefault(state, Counter())
        counts["repositories_reviewed"] += len(manifest["repositories"])
        counts["entrypoints_recorded"] += sum(len(repo["entrypoints"]) for repo in manifest["repositories"])
        for document in manifest["documents"]:
            counts["generated_outputs"] += 1
            counts[document["filing_status"]] += 1
            output_kind = document.get("output_kind")
            if output_kind is None:
                output_kind = (
                    "bundle"
                    if (
                        document.get("bundle_components")
                        or document.get("bundle_elements")
                        or "bundle" in str(document.get("attachment_variable") or "").casefold()
                    )
                    else "document"
                )
            is_bundle = output_kind == "bundle"
            is_fragment = output_kind == "fragment"
            counts["bundle_outputs" if is_bundle else "fragment_outputs" if is_fragment else "document_outputs"] += 1
            counts["attachment_outputs"] += not is_bundle
            evidence = {
                "form identifier": document.get("form_id") or _single_printed_form_id(document),
                # The printed PDF title is the strongest title evidence for
                # crosswalk identity; the interview's display title is only a
                # fallback when no printed title was extracted.
                "form name": document.get("printed_title") or document["title"],
            }
            eligible_form = not is_bundle and not is_fragment
            identity = (
                deterministic_form_identity(state, evidence)
                if eligible_form
                else {
                    "status": "not_individual_form",
                    "matches": [],
                }
            )
            mappings = (
                exact_form_crosswalk_matches(state, evidence)
                if document["filing_status"] == "court_filing" and eligible_form
                else []
            )
            if document["filing_status"] == "court_filing" and eligible_form:
                counts["registry_identity_" + identity["status"]] += 1
                counts["with_runtime_mapping" if mappings else "without_runtime_mapping"] += 1
                counts.setdefault("_distinct_form_keys", set()).add(_distinct_form_key(state, document))
            elif document["filing_status"] == "court_filing":
                counts["court_filing_bundles" if is_bundle else "court_filing_fragments"] += 1
            documents.append(
                {
                    "id": document["id"],
                    "state": state,
                    "repo": document["repo"],
                    "entrypoint": document.get("entrypoint"),
                    "template_paths": document.get("template_paths", []),
                    "source_urls": document.get("source_urls", []),
                    "stage": document.get("stage"),
                    "title": document["title"],
                    "printed_title": document.get("printed_title"),
                    "attachment_variable": document.get("attachment_variable"),
                    "output_kind": output_kind,
                    "form_id": document.get("form_id"),
                    "filing_status": document["filing_status"],
                    "publication_status": document["publication_status"],
                    "source_mapping_status": document["mapping_status"],
                    "registry_identity_status": identity["status"],
                    "registry_ids": [match["canonical_form_id"] for match in identity["matches"]],
                    "runtime_mappings": mappings,
                    "exclusion_reason": document.get("exclusion_reason"),
                }
            )
    for state, counts in states.items():
        counts["repositories_expected"] = sum(row["state"] == state for row in inventory["repositories"])
        counts["distinct_court_filing_forms"] = len(counts.pop("_distinct_form_keys", set()))
    return {
        "version": 1,
        "checked_at": inventory["checked_at"],
        "source_issue": inventory["source_issue"],
        "scope": "Declared repository/output inventory and current local registry; not live court or top-five query coverage.",
        "states": {state: dict(counts) for state, counts in states.items()},
        "inventory_errors": errors,
        "documents": documents,
    }


def _single_printed_form_id(document):
    identifiers = document.get("printed_form_ids") or []
    return identifiers[0] if len(identifiers) == 1 else None


def _distinct_form_key(state, document):
    identifier = document.get("form_id") or _single_printed_form_id(document)
    title = " ".join(str(document.get("printed_title") or document.get("title") or "").casefold().split())
    if identifier:
        return state, "id", re.sub(r"[^a-z0-9]", "", str(identifier).casefold()), title
    return state, "title", title
