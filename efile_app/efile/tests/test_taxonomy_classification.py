import json
from unittest.mock import patch

from django.test import override_settings

from efile.services.taxonomy_classification import (
    HierarchicalDocumentClassifier,
    exact_form_crosswalk_matches,
    primary_amount_in_controversy,
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
