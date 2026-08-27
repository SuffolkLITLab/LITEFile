import json
from unittest.mock import patch

from django.test import override_settings

from efile.services.taxonomy_classification import (
    HierarchicalDocumentClassifier,
    deterministic_form_identity,
    exact_form_crosswalk_matches,
    primary_amount_in_controversy,
    summarize_form_crosswalk_matches,
)


class FakeTaxonomy:
    base_url = "https://efile-test.example"

    def courts(self, _jurisdiction):
        return [
            {"route_key": "staging-court-7", "name": "Middlesex Probate and Family Court"},
            {"route_key": "staging-court-8", "name": "Norfolk Probate and Family Court"},
        ]

    def categories(self, _jurisdiction, court, _phase):
        assert court == "staging-court-7"
        return [{"route_key": "staging-category-4", "name": "Domestic Relations"}]

    def case_types(self, _jurisdiction, court, category, _phase):
        assert (court, category) == ("staging-court-7", "staging-category-4")
        return [{"route_key": "staging-type-9", "name": "Divorce 1B"}]

    def filing_types(self, _jurisdiction, court, category, case_type, _phase):
        assert (court, category, case_type) == (
            "staging-court-7",
            "staging-category-4",
            "staging-type-9",
        )
        return [
            {
                "route_key": "staging-filing-12",
                "name": "Complaint for Divorce - Irretrievable Breakdown 1B",
            }
        ]


@patch("efile.services.taxonomy_classification.chat_completion")
def test_hierarchy_uses_references_then_restores_live_names_and_route_keys(chat_completion):
    chat_completion.side_effect = [
        {"status": "selected", "selection_ref": "C001", "confidence": 0.91, "evidence": ["Middlesex"]},
        {"status": "selected", "selection_ref": "C001", "confidence": 0.92, "evidence": ["divorce"]},
        {"status": "selected", "selection_ref": "C001", "confidence": 0.93, "evidence": ["§ 1B"]},
        {"status": "selected", "selection_ref": "C001", "confidence": 0.94, "evidence": ["Complaint"]},
    ]
    classifier = HierarchicalDocumentClassifier(taxonomy=FakeTaxonomy(), model="test-model")

    run = classifier.classify(
        "massachusetts",
        {
            "court name": "Middlesex Division",
            "form identifier": "CJD 101B",
            "form name": "Complaint for Divorce under G.L. c. 208, § 1B",
            "filing phase": "initial",
        },
        "COMPLAINT FOR DIVORCE UNDER G.L. c. 208, § 1B",
    )

    assert run.selections["case type"]["name"] == "Divorce 1B"
    assert run.selections["case type"]["route_key"] == "staging-type-9"
    assert run.selections["filing type"]["name"] == "Complaint for Divorce - Irretrievable Breakdown 1B"
    assert run.metadata["prompt_version"] == "v2"
    assert run.metadata["taxonomy_endpoint"] == "https://efile-test.example"
    assert run.metadata["form_crosswalk_summary"]["route_resolution"] == "exact"


@patch("efile.services.taxonomy_classification.chat_completion")
def test_unoffered_reference_is_rejected_in_application_code(chat_completion):
    chat_completion.return_value = {
        "status": "selected",
        "selection_ref": "C999",
        "confidence": 1,
        "evidence": [],
    }
    classifier = HierarchicalDocumentClassifier(taxonomy=FakeTaxonomy(), model="test-model")

    run = classifier.classify("massachusetts", {"court name": "Middlesex"}, "Middlesex")

    assert run.selections["court"]["status"] == "abstain"
    assert "case category" not in run.selections


def test_amount_prefill_requires_one_claim_like_express_amount():
    evidence = {
        "monetary amounts": [
            {
                "label": "Amount in controversy",
                "raw": "$1,275.00",
                "amount": "1275.00",
                "currency": "USD",
            }
        ]
    }
    assert primary_amount_in_controversy(evidence) == "1275.00"

    evidence["monetary amounts"].append({"label": "Damages demand", "amount": "500"})
    assert primary_amount_in_controversy(evidence) == ""


def test_crosswalk_requires_an_exact_form_match(tmp_path):
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(
        json.dumps(
            {
                "registry": [
                    {
                        "form": {
                            "canonical_id": "MA-CJD-101B",
                            "jurisdiction": "massachusetts",
                            "form_id": "CJD 101B",
                            "canonical_name": "Complaint for Divorce under G.L. c. 208, § 1B",
                            "aliases": ["1B Divorce Complaint"],
                        },
                        "mappings": [
                            {
                                "category": "Domestic Relations",
                                "case_type": "Divorce 1B",
                                "filing_type": "Complaint for Divorce - Irretrievable Breakdown 1B",
                                "catalog_status": "current",
                                "association_status": "unverified_suggestion",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with override_settings(FORM_CODE_CROSSWALK_PATH=crosswalk_path):
        matches = exact_form_crosswalk_matches("massachusetts", {"form identifier": "CJD-101B"})
        misses = exact_form_crosswalk_matches("massachusetts", {"form identifier": "CJD 101"})

    assert matches[0]["case_type"] == "Divorce 1B"
    assert matches[0]["match_basis"] == "exact form identifier"
    assert misses == []


def test_form_identifier_normalization_handles_ocr_punctuation(tmp_path):
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(
        json.dumps(
            {
                "registry": [
                    {
                        "form": {
                            "canonical_id": "MA-CJD-101B",
                            "jurisdiction": "massachusetts",
                            "form_id": "CJD 101B",
                            "canonical_name": "Complaint for Divorce under G.L. c. 208, § 1B",
                            "is_form": True,
                            "is_efileable": True,
                        },
                        "mappings": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with override_settings(FORM_CODE_CROSSWALK_PATH=crosswalk_path):
        identity = deterministic_form_identity(
            "massachusetts",
            {"form identifier": "CJ-D 101B"},
        )

    assert identity["status"] == "matched"
    assert identity["matches"][0]["canonical_form_id"] == "MA-CJD-101B"


def test_conflicting_identifier_does_not_fall_back_to_title(tmp_path):
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(
        json.dumps(
            {
                "registry": [
                    {
                        "form": {
                            "canonical_id": "MA-CJD-101B",
                            "jurisdiction": "massachusetts",
                            "form_id": "CJD 101B",
                            "canonical_name": "Complaint for Divorce under G.L. c. 208, § 1B",
                            "is_form": True,
                            "is_efileable": True,
                        },
                        "mappings": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with override_settings(FORM_CODE_CROSSWALK_PATH=crosswalk_path):
        identity = deterministic_form_identity(
            "massachusetts",
            {
                "form identifier": "CJD 101",
                "form name": "Complaint for Divorce under G.L. c. 208, § 1B",
            },
        )

    assert identity["status"] == "unmatched"


def test_reused_form_id_is_ambiguous_without_title(tmp_path):
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(
        json.dumps(
            {
                "registry": [
                    {
                        "form": {
                            "canonical_id": "IL-ANS-1",
                            "jurisdiction": "illinois",
                            "form_id": "ANS",
                            "canonical_name": "Answer or Response",
                            "is_form": True,
                            "is_efileable": True,
                        },
                        "mappings": [],
                    },
                    {
                        "form": {
                            "canonical_id": "IL-ANS-2",
                            "jurisdiction": "illinois",
                            "form_id": "ANS",
                            "canonical_name": "Counterclaims",
                            "is_form": True,
                            "is_efileable": True,
                        },
                        "mappings": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with override_settings(FORM_CODE_CROSSWALK_PATH=crosswalk_path):
        ambiguous = deterministic_form_identity("illinois", {"form identifier": "ANS"})
        narrowed = deterministic_form_identity(
            "illinois",
            {"form identifier": "ANS", "form name": "Counterclaims"},
        )

    assert ambiguous["status"] == "ambiguous"
    assert narrowed["status"] == "matched"
    assert narrowed["matches"][0]["canonical_form_id"] == "IL-ANS-2"


def test_known_bad_form_association_is_not_a_runtime_match(tmp_path):
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(
        json.dumps(
            {
                "registry": [
                    {
                        "form": {
                            "canonical_id": "MA-CJD-102",
                            "jurisdiction": "massachusetts",
                            "form_id": "CJD 102",
                            "canonical_name": "Complaint for Separate Support",
                            "is_form": True,
                            "is_efileable": True,
                            "runtime_mapping_policy": {"runtime": "blocked"},
                        },
                        "mappings": [
                            {
                                "category": "Wrong category",
                                "case_type": "Wrong case type",
                                "filing_type": "Wrong filing type",
                                "catalog_status": "current",
                                "association_status": "unverified_suggestion",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with override_settings(FORM_CODE_CROSSWALK_PATH=crosswalk_path):
        matches = exact_form_crosswalk_matches("massachusetts", {"form identifier": "CJD 102"})

    assert matches == []


def _two_forms_sharing_an_id(canonical_ids):
    return {
        "registry": [
            {
                "form": {
                    "canonical_id": canonical_id,
                    "jurisdiction": "illinois",
                    "form_id": "ANS",
                    "canonical_name": name,
                    "is_form": True,
                    "is_efileable": True,
                },
                "mappings": [
                    {
                        "category": category,
                        "case_type": case_type,
                        "filing_type": name,
                        "catalog_status": "current",
                        "association_status": "unverified_suggestion",
                    }
                ],
            }
            for canonical_id, name, category, case_type in zip(
                canonical_ids,
                ["Answer or Response", "Counterclaims"],
                ["Civil", "Domestic Relations"],
                ["Small Claims", "Dissolution"],
                strict=True,
            )
        ]
    }


def test_an_ambiguous_identity_yields_no_crosswalk_mappings(tmp_path):
    """Two forms sharing an id are two forms, and neither one's route is known.

    Returning both blends a category from one form with a filing type from the
    other into a single list of hints, with nothing left in the result to say
    the identity was never settled -- so a caller narrows the Tyler hierarchy
    using a form the filer did not upload.
    """

    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(json.dumps(_two_forms_sharing_an_id(["IL-ANS-1", "IL-ANS-2"])), encoding="utf-8")

    with override_settings(FORM_CODE_CROSSWALK_PATH=crosswalk_path):
        identity = deterministic_form_identity("illinois", {"form identifier": "ANS"})
        matches = exact_form_crosswalk_matches("illinois", {"form identifier": "ANS"})
        narrowed = exact_form_crosswalk_matches(
            "illinois",
            {"form identifier": "ANS", "form name": "Counterclaims"},
        )

    assert identity["status"] == "ambiguous"
    assert matches == []
    # An exact title still settles it, so the safe path is not lost.
    assert [match["case_type"] for match in narrowed] == ["Dissolution"]


def test_entries_missing_a_canonical_id_are_not_collapsed_into_one_form(tmp_path):
    """A shared *absent* id is not agreement -- it is two entries and no claim."""
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(json.dumps(_two_forms_sharing_an_id([None, None])), encoding="utf-8")

    with override_settings(FORM_CODE_CROSSWALK_PATH=crosswalk_path):
        identity = deterministic_form_identity("illinois", {"form identifier": "ANS"})
        matches = exact_form_crosswalk_matches("illinois", {"form identifier": "ANS"})

    assert identity["status"] == "ambiguous"
    assert matches == []


def test_a_single_entry_without_a_canonical_id_still_matches(tmp_path):
    """One candidate is unambiguous whether or not the registry named it."""
    registry = _two_forms_sharing_an_id([None, None])
    registry["registry"] = registry["registry"][:1]
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(json.dumps(registry), encoding="utf-8")

    with override_settings(FORM_CODE_CROSSWALK_PATH=crosswalk_path):
        identity = deterministic_form_identity("illinois", {"form identifier": "ANS"})
        matches = exact_form_crosswalk_matches("illinois", {"form identifier": "ANS"})

    assert identity["status"] == "matched"
    assert [match["case_type"] for match in matches] == ["Small Claims"]


def test_crosswalk_summary_preserves_narrowed_case_type_with_multiple_filings():
    summary = summarize_form_crosswalk_matches(
        [
            {
                "category": "Civil",
                "case_type": "Small Claims",
                "filing_type": "Small Claims $1,000 or less",
                "filing_phase": "initial",
            },
            {
                "category": "Civil",
                "case_type": "Small Claims",
                "filing_type": "Small Claims $1,001 through $5,000",
                "filing_phase": "initial",
            },
        ],
        identity_status="matched",
    )

    assert summary["route_resolution"] == "narrowed"
    assert summary["constraint_confidence"] == "advisory"
    assert summary["level_status"] == {
        "category": "resolved",
        "case_type": "resolved",
        "filing_type": "ambiguous",
    }
    assert summary["candidate_counts"] == {
        "category": 1,
        "case_type": 1,
        "filing_type": 2,
    }
    assert summary["next_evidence"] == ["amount_in_controversy"]
