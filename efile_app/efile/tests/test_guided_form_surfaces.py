"""Guided-interview form IDs must work in extraction and Find code search."""

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from efile.services.document_extractions import keyword_document_analysis
from efile.services.filing_code_search import (
    current_index,
    indexed_path,
    refresh_index,
    search_paths,
    search_tokens,
)
from efile.services.taxonomy_classification import (
    exact_form_crosswalk_matches,
    scan_document_for_form_identifiers,
)


@pytest.mark.parametrize(
    ("jurisdiction", "printed_id", "canonical_name"),
    [
        ("illinois", "ATJ 251.5", "FINANCIAL AFFIDAVIT"),
        ("illinois", "ATJ 108.4", "PARENTING PLAN"),
        ("vermont", "400-00813B", "Financial Affidavit 813B"),
        ("vermont", "100-00127", "Financial Disclosure"),
    ],
)
def test_printed_guided_form_ids_are_found_by_registry_and_keyword_extraction(
    jurisdiction,
    printed_id,
    canonical_name,
):
    text = f"Court form\n{printed_id}\nCase No. 2026-CV-12345"
    scan = scan_document_for_form_identifiers(jurisdiction, text)
    assert scan["status"] == "matched"
    assert scan["deterministic_match"]["form_id"] == printed_id
    assert scan["deterministic_match"]["form_name"] == canonical_name

    # Exercise the no-AI production extraction path with controlled PDF text;
    # the form-ID scanner itself and current registry remain real.
    with (
        patch("efile.services.document_extractions._source_text", return_value=(text, 1)),
        patch("efile.services.document_extractions._searchable_pdf_text", return_value=text),
        patch("efile.services.document_extractions._pdf_form_values", return_value=""),
        patch(
            "efile.services.document_extractions.extract_fields_from_file",
            side_effect=AssertionError("keyword analysis must not call a model"),
        ),
    ):
        analysis = keyword_document_analysis("controlled.pdf", jurisdiction)

    assert analysis["evidence"]["form identifier"] == printed_id
    assert analysis["evidence"]["form name"] == canonical_name
    assert analysis["evidence"]["docket number"] == "2026-CV-12345"
    assert analysis["metadata"]["analysis_mode"] == "keyword"
    expected_labels = {
        "ATJ 251.5": {"Financial Affidavit", "Financial Affidavit Filed"},
        "ATJ 108.4": {"Parenting Plan"},
        "400-00813B": {"813B Financial Affidavit"},
        "100-00127": {"Small Claims - Financial Disclosure Affidavit"},
    }
    summary = analysis["metadata"]["form_crosswalk_summary"]
    assert set(summary["filing_type_candidates"]) == expected_labels[printed_id]
    assert summary["constraint_confidence"] == "advisory"
    if printed_id == "ATJ 251.5":
        assert summary["level_status"]["filing_type"] == "ambiguous"
        assert not analysis["guesses"].get("filing type")


@pytest.mark.parametrize(
    ("jurisdiction", "printed_id"),
    [
        ("illinois", "400-00813B"),
        ("illinois", "100-00127"),
        ("vermont", "ATJ 251.5"),
        ("vermont", "ATJ 108.4"),
    ],
)
def test_guided_form_ids_do_not_cross_jurisdiction_registry_boundaries(jurisdiction, printed_id):
    result = scan_document_for_form_identifiers(jurisdiction, f"Form {printed_id}")
    assert result["status"] == "unmatched"
    assert result.get("deterministic_match") is None


def _path(state, court, category, case_type, filing_type, initial):
    return indexed_path(
        state,
        {
            "court": {"code": court, "name": f"{court.title()} Court"},
            "case_category": {"code": category.lower().replace(" ", "-"), "name": category},
            "case_type": {"code": case_type.lower().replace(" ", "-"), "name": case_type},
            "filing_type": {"code": filing_type.lower().replace(" ", "-"), "name": filing_type},
        },
        initial,
    )


@pytest.mark.django_db
def test_guided_form_ids_retrieve_only_their_scoped_find_code_paths():
    paths = {
        "illinois": [
            _path("illinois", "il-family", "Family", "Divorce", "Financial Affidavit", False),
            _path("illinois", "il-parenting", "Family", "Parenting Responsibilities", "Parenting Plan", False),
            _path("illinois", "il-civil", "Civil", "Small Claims", "Financial Affidavit", False),
        ],
        "vermont": [
            _path("vermont", "vt-family", "Family", "Divorce", "813B Financial Affidavit", False),
            _path(
                "vermont",
                "vt-small-claims",
                "Civil",
                "Small Claims $1,000 or less",
                "Small Claims - Financial Disclosure Affidavit",
                False,
            ),
        ],
    }

    for jurisdiction, entries in paths.items():
        with patch("efile.services.filing_code_search.catalog_entries", return_value=iter(entries)):
            refresh_index(jurisdiction, transport="legacy")
        index = current_index(jurisdiction)
        if jurisdiction == "illinois":
            expected = {
                "ATJ 251.5": "Financial Affidavit",
                "ATJ 108.4": "Parenting Plan",
            }
            for query, filing_label in expected.items():
                assert search_tokens(query, jurisdiction, query=True, path_query=True)
                results = search_paths(index, query, initial=False)
                assert results["total"] == 1
                assert results["results"][0]["filing_type"]["name"] == filing_label
            assert search_paths(index, "ATJ 251.5", initial=False)["results"][0]["case_type"]["name"] == "Divorce"
            assert search_paths(index, "ATJ 108.4", initial=False)["results"][0]["case_type"]["name"] == (
                "Parenting Responsibilities"
            )
            assert search_paths(index, "ATJ 251.5", initial=False)["results"][0]["case_category"]["name"] == "Family"
        else:
            expected = {
                "400-00813B": "813B Financial Affidavit",
                "100-00127": "Small Claims - Financial Disclosure Affidavit",
            }
            for query, filing_label in expected.items():
                assert search_tokens(query, jurisdiction, query=True, path_query=True)
                results = search_paths(index, query, initial=False)
                assert results["total"] == 1
                assert results["results"][0]["filing_type"]["name"] == filing_label

    # Same spelling in the other state's document must not generate a result.
    assert search_paths(current_index("illinois"), "400-00813B", initial=False)["total"] == 0
    assert search_paths(current_index("vermont"), "ATJ 251.5", initial=False)["total"] == 0


def test_every_illinois_generated_alias_has_source_and_registry_parity():
    data_dir = Path(__file__).resolve().parents[1] / "data"
    aliases = json.loads((data_dir / "guided_form_search_aliases.json").read_text())
    inventory = json.loads((data_dir / "guided_interview_inventory.json").read_text())
    manifests = [json.loads((data_dir / filename).read_text()) for filename in inventory["manifest_files"]]
    documents = [document for manifest in manifests for document in manifest["documents"]]

    def compact(value):
        return re.sub(r"[^a-z0-9]", "", str(value).casefold())

    for rule in aliases["path_aliases"]:
        if "illinois" not in rule["jurisdictions"]:
            continue
        concepts = rule["concepts"]
        concept_ids = {compact(term) for concept in concepts for term in aliases["concepts"][concept]["terms"]}
        source = rule.get("source_output")
        source_documents = [
            document
            for document in documents
            if (
                (source and (document["id"] == source or document["id"].startswith(source + ":")))
                or any(
                    compact(identifier) in concept_ids
                    for identifier in ([document.get("form_id")] + (document.get("printed_form_ids") or []))
                    if identifier
                )
            )
        ]
        assert source_documents, f"No inventory output backs alias {source}"
        source_ids = {
            compact(identifier)
            for document in source_documents
            for identifier in ([document.get("form_id")] + (document.get("printed_form_ids") or []))
            if identifier
        }
        concept_ids = {compact(term) for concept in concepts for term in aliases["concepts"][concept]["terms"]}
        assert source_ids & concept_ids, f"No printed form ID backs alias {source}"
        for concept in concepts:
            for printed_id in aliases["concepts"][concept]["terms"]:
                matches = exact_form_crosswalk_matches("illinois", {"form identifier": printed_id})
                assert any(match.get("filing_type") in rule["filing_type"] for match in matches), (
                    f"Registry mapping for {printed_id} lacks alias label {rule['filing_type']}"
                )

        category = (rule.get("case_category") or ["Civil"])[0]
        case_type = (rule.get("case_type") or ["Other"])[0]
        filing_type = rule["filing_type"][0]
        query = aliases["concepts"][concepts[0]]["terms"][0]
        concept_tokens = {"concept" + compact(key) for key in concepts}
        court_codes = rule.get("court_codes") or []
        court_prefixes = rule.get("court_code_prefixes") or []
        court_code = (
            court_codes[0] if court_codes else (court_prefixes[0] + "parity" if court_prefixes else "parity-court")
        )
        indexed = _path("illinois", court_code, category, case_type, filing_type, rule["initial"])
        assert any(concept in indexed["filing_terms"] for concept in concept_tokens), (
            f"Indexed filing path omits alias concept for {source}"
        )
        assert concept_tokens & search_tokens(query, "illinois", query=True, path_query=True)
        wrong_label = _path("illinois", court_code, category, case_type, "Other Document Not Listed", rule["initial"])
        assert not any(concept in wrong_label["filing_terms"] for concept in concept_tokens), (
            f"Alias for {source} leaked onto a different filing label"
        )
        if court_codes:
            foreign_court = _path("illinois", "other-court-code", category, case_type, filing_type, rule["initial"])
            assert not any(concept in foreign_court["filing_terms"] for concept in concept_tokens), (
                f"Court-scoped alias for {source} leaked to a different provider court"
            )
