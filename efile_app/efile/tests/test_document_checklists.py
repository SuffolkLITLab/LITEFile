"""Tests for partner-configured document checklists.

Most tests build a small YAML configuration in a temporary directory, so they
describe the contract partners write against rather than the Illinois content of
the moment. The last group checks the shipped Illinois configuration against the
names the courts actually publish.
"""

from unittest.mock import patch

import pytest
import yaml

from efile.services.document_checklists import normalize_name, resolve_document_checklist
from efile.utils.config_loader import JurisdictionConfigLoader

BASE_CONFIG = {
    "base_case_types": {
        "name_change": {
            "matches": {"names": ["Name Change"]},
            "documents": {
                "petition": {"label": "Request to change a name", "requirement": "always", "role": "lead"},
                "fee_waiver": {"label": "Request to waive court fees", "requirement": "sometimes"},
            },
        }
    }
}

STATE_CONFIG = {
    "case_types": {
        "name_change": {
            "extends": "base_case_types.name_change",
            "matches": {"names": ["Name Change", "Change of Name"], "aliases": ["Petition - Change of Name"]},
            "documents": {
                "publication_notice": {"label": "Proof of newspaper notice", "requirement": "usually"},
                "minor_consent": {
                    "label": "Consent from the child",
                    "requirement": "sometimes",
                    "when": {"lead_filing_type_names": ["Request for Name Change (Minor Children)"]},
                },
            },
        },
        "eviction": {
            "matches": {"names": ["Residential - Eviction"]},
            "documents": {"answer": {"label": "Answer", "requirement": "always"}},
        },
    },
    "case_categories": {
        "miscellaneous_remedy": {
            "matches": {"names": ["Miscellaneous Remedy"]},
            "documents": {"supporting_records": {"label": "Papers that back up your side", "requirement": "usually"}},
        }
    },
    "court_specific_requirements": {
        "cook:cd1": {
            "case_types": {
                "name_change": {
                    "documents": {
                        "publication_notice": {"requirement": "always"},
                        "cover_sheet": {"label": "County cover sheet", "requirement": "always"},
                        "fee_waiver": {"include": False},
                    }
                }
            }
        }
    },
}


@pytest.fixture
def checklist_config(tmp_path):
    """Point the checklist resolver at a throwaway partner configuration."""

    (tmp_path / "base-case-types.yaml").write_text(yaml.safe_dump(BASE_CONFIG))
    (tmp_path / "states").mkdir(exist_ok=True)
    (tmp_path / "states" / "testland.yaml").write_text(yaml.safe_dump(STATE_CONFIG))

    loader = JurisdictionConfigLoader(config_dir=tmp_path)
    with patch("efile.services.document_checklists.config_loader", loader):
        yield loader


def test_normalize_name_folds_case_spacing_and_dashes():
    assert normalize_name("  Petition for Dissolution of Marriage – Children ") == (
        "petition for dissolution of marriage - children"
    )
    assert normalize_name("Affidavit Filed    ") == "affidavit filed"
    assert normalize_name(None) == ""


def test_case_type_checklist_merges_base_and_state_and_orders_by_requirement(checklist_config):
    checklist = resolve_document_checklist("testland", case_type_name="Change of Name")

    assert list(checklist) == ["petition", "publication_notice", "fee_waiver"]
    assert checklist["petition"] == {
        "label": "Request to change a name",
        "requirement": "always",
        "role": "lead",
    }
    assert checklist["publication_notice"]["requirement"] == "usually"


def test_checklist_holds_no_court_codes(checklist_config):
    checklist = resolve_document_checklist("testland", case_type_name="Name Change")

    for item in checklist.values():
        assert set(item) <= {"label", "requirement", "description", "role"}


def test_matching_ignores_case_spacing_and_dash_style(checklist_config):
    assert resolve_document_checklist("testland", case_type_name="  CHANGE   OF NAME ")
    assert resolve_document_checklist("testland", case_type_name="Residential – Eviction")


def test_matching_accepts_configured_aliases(checklist_config):
    assert resolve_document_checklist("testland", case_type_name="Petition - Change of Name")


def test_matching_is_not_fuzzy(checklist_config):
    """A name nobody configured gets no checklist, rather than a near miss."""

    assert resolve_document_checklist("testland", case_type_name="Name Change Petition") == {}
    assert resolve_document_checklist("testland", case_type_name="Eviction") == {}


def test_court_override_adds_changes_and_removes_items(checklist_config):
    everywhere = resolve_document_checklist("testland", case_type_name="Name Change")
    cook = resolve_document_checklist("testland", court_code="cook:cd1", case_type_name="Name Change")

    assert everywhere["publication_notice"]["requirement"] == "usually"
    assert "fee_waiver" in everywhere
    assert "cover_sheet" not in everywhere

    assert cook["publication_notice"]["requirement"] == "always"
    assert cook["cover_sheet"]["label"] == "County cover sheet"
    assert "fee_waiver" not in cook
    # An override changes one item without dropping the rest of the list.
    assert cook["petition"]["label"] == "Request to change a name"


def test_court_override_does_not_leak_to_other_courts(checklist_config):
    dupage = resolve_document_checklist("testland", court_code="dupage", case_type_name="Change of Name")

    assert "cover_sheet" not in dupage


def test_filing_type_condition_filters_items(checklist_config):
    without_lead = resolve_document_checklist("testland", case_type_name="Name Change")
    minor = resolve_document_checklist(
        "testland",
        case_type_name="Name Change",
        lead_filing_type_name="Request for Name Change (Minor Children)",
    )
    adult = resolve_document_checklist(
        "testland",
        case_type_name="Name Change",
        lead_filing_type_name="Request for Name Change (Adult)",
    )

    assert "minor_consent" not in without_lead
    assert "minor_consent" in minor
    assert "minor_consent" not in adult


def test_category_guidance_is_the_fallback(checklist_config):
    checklist = resolve_document_checklist(
        "testland",
        case_category_name="Miscellaneous Remedy",
        case_type_name="Something The Config Does Not Know",
    )

    assert list(checklist) == ["supporting_records"]


def test_case_type_checklist_replaces_category_guidance(checklist_config):
    checklist = resolve_document_checklist(
        "testland",
        case_category_name="Miscellaneous Remedy",
        case_type_name="Name Change",
    )

    assert "supporting_records" not in checklist
    assert "petition" in checklist


def test_unmatched_case_returns_no_checklist(checklist_config):
    assert resolve_document_checklist("testland", case_type_name="Tax Sale") == {}
    assert resolve_document_checklist("testland") == {}
    assert resolve_document_checklist("") == {}


def test_unknown_requirement_falls_back_to_sometimes(tmp_path):
    (tmp_path / "base-case-types.yaml").write_text(yaml.safe_dump({}))
    (tmp_path / "states").mkdir(exist_ok=True)
    (tmp_path / "states" / "testland.yaml").write_text(
        yaml.safe_dump(
            {
                "case_types": {
                    "name_change": {
                        "matches": {"names": ["Name Change"]},
                        "documents": {"petition": {"label": "Petition", "requirement": "mandatory"}},
                    }
                }
            }
        )
    )
    loader = JurisdictionConfigLoader(config_dir=tmp_path)

    with patch("efile.services.document_checklists.config_loader", loader):
        checklist = resolve_document_checklist("testland", case_type_name="Name Change")

    assert checklist["petition"]["requirement"] == "sometimes"


class TestShippedIllinoisConfig:
    """Check the Illinois configuration against names the live courts publish."""

    def test_cook_county_name_change(self):
        checklist = resolve_document_checklist(
            "illinois",
            court_code="cook:cd1",
            case_category_name="Miscellaneous",
            case_type_name="Name Change",
            lead_filing_type_name="Petition for Name Change",
        )

        assert checklist["petition"]["requirement"] == "always"
        assert checklist["county_division_cover_sheet"]["requirement"] == "always"
        assert "minor_consent" not in checklist

    def test_name_change_outside_cook_county(self):
        checklist = resolve_document_checklist(
            "illinois",
            court_code="lake",
            case_category_name="Miscellaneous Remedy",
            case_type_name="Change of Name",
            lead_filing_type_name="Request for Name Change (Minor Children)",
        )

        assert "county_division_cover_sheet" not in checklist
        assert "minor_consent" in checklist
        assert checklist["publication_notice"]["requirement"] == "usually"

    def test_dissolution_names_match_despite_dash_style(self):
        """Cook County spells one case type with a dash and its pair with a hyphen."""

        with_children = resolve_document_checklist(
            "illinois",
            court_code="cook:dr1",
            case_type_name="Petition for Dissolution of Marriage – Children",
        )
        without_children = resolve_document_checklist(
            "illinois",
            court_code="cook:dr1",
            case_type_name="Petition for Dissolution of Marriage - No Children",
        )

        assert with_children["petition"]["requirement"] == "always"
        assert with_children["financial_affidavit"]["requirement"] == "always"
        assert without_children["domestic_relations_cover_sheet"]["requirement"] == "always"

    def test_dissolution_outside_cook_county_keeps_state_wide_levels(self):
        checklist = resolve_document_checklist(
            "illinois",
            court_code="dupage",
            case_category_name="Dissolution (Divorce) with Children",
            case_type_name="Dissolution (with children)",
        )

        assert checklist["financial_affidavit"]["requirement"] == "usually"
        assert "domestic_relations_cover_sheet" not in checklist

    def test_eviction_checklist_depends_on_who_is_filing(self):
        landlord = resolve_document_checklist(
            "illinois",
            court_code="cook:cvd1",
            case_type_name="Eviction - Possession - Residential Complaint Filed - Non-Jury",
            lead_filing_type_name="Complaint / Petition - Eviction - Residential - Possession Only - Fee",
        )
        tenant = resolve_document_checklist(
            "illinois",
            court_code="cook:cvd1",
            case_type_name="Eviction - Possession - Residential Complaint Filed - Non-Jury",
            lead_filing_type_name="Appearance Filed - Eviction - Possession Only",
        )

        assert "complaint" in landlord
        assert "answer" not in landlord
        assert "appearance" in tenant
        assert "answer" in tenant
        assert tenant["early_resolution_program_notice"]["requirement"] == "always"

    def test_category_guidance_for_a_case_type_with_no_checklist(self):
        checklist = resolve_document_checklist(
            "illinois",
            court_code="dupage",
            case_category_name="Small Claims",
            case_type_name="Contract - Debt Collection (Seller/Plaintiff) (Up to $2,500)",
        )

        assert list(checklist) == ["supporting_records", "proof_of_service", "fee_waiver"]
