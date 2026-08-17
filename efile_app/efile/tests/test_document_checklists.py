"""Tests for partner-configured document checklists.

Most tests build a small YAML configuration in a temporary directory, so they
describe the contract partners write against rather than the Illinois content of
the moment. The last group checks the shipped Illinois configuration against the
names the courts actually publish.
"""

from unittest.mock import patch

import pytest
import yaml

from efile.services.document_checklists import (
    normalize_name,
    party_type_keywords_for_role,
    resolve_document_checklist,
    resolve_filer_roles,
    resolve_plan_guidance,
)
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
            "filer_roles": {
                "landlord": {
                    "label": "The landlord",
                    "party_type_keywords": ["plaintiff", "petitioner"],
                    "suggested_when": {"lead_filing_type_names": ["Complaint"]},
                },
                "tenant": {"label": "The tenant"},
            },
            "documents": {
                "complaint": {"label": "Complaint", "requirement": "always", "for_roles": ["landlord"]},
                "answer": {"label": "Answer", "requirement": "always", "for_roles": ["tenant"]},
                "proof_of_service": {
                    "label": "Proof the other side got a copy",
                    "requirement": "usually",
                    "by_role": {
                        "landlord": {"label": "Proof the tenant got a copy"},
                        "tenant": {"label": "Proof the landlord got a copy", "requirement": "always"},
                    },
                },
                "photographs": {"label": "Photographs", "requirement": "sometimes"},
            },
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
    # An en dash where the configuration has a hyphen, on a case type with sides.
    assert resolve_document_checklist("testland", case_type_name="Residential – Eviction", filer_role="tenant")


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


def eviction(filer_role, lead_filing_type_name=""):
    return resolve_document_checklist(
        "testland",
        case_type_name="Residential - Eviction",
        lead_filing_type_name=lead_filing_type_name,
        filer_role=filer_role,
    )


def test_an_item_belongs_only_to_the_sides_it_names(checklist_config):
    assert "complaint" in eviction("landlord")
    assert "answer" not in eviction("landlord")
    assert "answer" in eviction("tenant")
    assert "complaint" not in eviction("tenant")


def test_an_item_that_names_no_side_belongs_to_everyone(checklist_config):
    assert "photographs" in eviction("landlord")
    assert "photographs" in eviction("tenant")


def test_a_shared_item_is_worded_for_the_side_reading_it(checklist_config):
    assert eviction("landlord")["proof_of_service"]["label"] == "Proof the tenant got a copy"
    assert eviction("tenant")["proof_of_service"]["label"] == "Proof the landlord got a copy"


def test_a_side_can_need_a_shared_item_more_than_the_other(checklist_config):
    assert eviction("landlord")["proof_of_service"]["requirement"] == "usually"
    assert eviction("tenant")["proof_of_service"]["requirement"] == "always"


def test_an_override_cannot_turn_an_item_into_a_different_document(tmp_path):
    """Only wording and requirement bend per side; identity does not."""

    (tmp_path / "base-case-types.yaml").write_text(yaml.safe_dump({}))
    (tmp_path / "states").mkdir(exist_ok=True)
    (tmp_path / "states" / "testland.yaml").write_text(
        yaml.safe_dump(
            {
                "case_types": {
                    "eviction": {
                        "matches": {"names": ["Eviction"]},
                        "filer_roles": {"tenant": {"label": "The tenant"}},
                        "documents": {
                            "lease": {
                                "label": "The lease",
                                "requirement": "usually",
                                "by_role": {"tenant": {"role": "lead", "for_roles": ["landlord"]}},
                            }
                        },
                    }
                }
            }
        )
    )
    loader = JurisdictionConfigLoader(config_dir=tmp_path)
    with patch("efile.services.document_checklists.config_loader", loader):
        checklist = resolve_document_checklist("testland", case_type_name="Eviction", filer_role="tenant")

    assert "role" not in checklist["lease"]
    assert "for_roles" not in checklist["lease"]


def test_a_case_with_sides_has_no_list_until_one_is_chosen(checklist_config):
    assert eviction("") == {}
    assert eviction("squatter") == {}


def test_sides_are_offered_with_the_likely_one_marked(checklist_config):
    roles = resolve_filer_roles("testland", case_type_name="Residential - Eviction", lead_filing_type_name="Complaint")

    assert [role["id"] for role in roles] == ["landlord", "tenant"]
    assert roles[0]["label"] == "The landlord"
    assert roles[0]["suggested"] is True
    # A side with no suggested_when is never the suggestion.
    assert roles[1]["suggested"] is False


def test_a_case_without_sides_offers_none(checklist_config):
    assert resolve_filer_roles("testland", case_type_name="Name Change") == []
    assert resolve_filer_roles("testland", case_type_name="Nothing Configured") == []


def test_a_side_carries_the_words_that_find_its_party_type(checklist_config):
    keywords = party_type_keywords_for_role(
        "testland",
        case_type_name="Residential - Eviction",
        filer_role="landlord",
    )

    assert keywords == ["plaintiff", "petitioner"]
    assert party_type_keywords_for_role("testland", case_type_name="Residential - Eviction", filer_role="") == []
    assert party_type_keywords_for_role("testland", case_type_name="Name Change", filer_role="landlord") == []


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

    def eviction_checklist(self, filer_role):
        return resolve_document_checklist(
            "illinois",
            court_code="cook:cvd1",
            case_type_name="Eviction - Possession - Residential Complaint Filed - Non-Jury",
            lead_filing_type_name="Complaint / Petition - Eviction - Residential - Possession Only - Fee",
            filer_role=filer_role,
        )

    def test_eviction_checklist_depends_on_who_is_filing(self):
        landlord = self.eviction_checklist("landlord")
        tenant = self.eviction_checklist("tenant")

        assert "complaint" in landlord
        assert "answer" not in landlord
        assert "appearance" not in landlord
        assert "complaint" not in tenant
        assert "appearance" in tenant
        assert "answer" in tenant
        # Cook's Early Resolution Program notice is served by the landlord.
        assert "early_resolution_program_notice" in landlord
        assert "early_resolution_program_notice" not in tenant

    def test_each_side_of_an_eviction_is_addressed_as_themselves(self):
        landlord = self.eviction_checklist("landlord")
        tenant = self.eviction_checklist("tenant")

        assert landlord["landlord_notice"]["label"] == "The notice you gave the tenant"
        assert tenant["landlord_notice"]["label"] == "The written notice your landlord gave you"
        # The notice is what makes an eviction filable, and only one side files it.
        assert landlord["landlord_notice"]["requirement"] == "always"
        assert tenant["landlord_notice"]["requirement"] == "sometimes"
        assert "tenant" in landlord["proof_of_service"]["label"]
        assert "landlord" in tenant["proof_of_service"]["label"]

    def test_an_eviction_has_no_checklist_until_a_side_is_chosen(self):
        """Half a list is worse than none: the rest is the other party's."""

        assert self.eviction_checklist("") == {}
        assert self.eviction_checklist("not-a-side") == {}

    def test_the_sides_of_an_eviction_are_offered_with_a_suggestion(self):
        roles = resolve_filer_roles(
            "illinois",
            court_code="cook:cvd1",
            case_type_name="Eviction - Possession - Residential Complaint Filed - Non-Jury",
            lead_filing_type_name="Appearance Filed - Eviction - Possession Only",
        )

        assert [role["id"] for role in roles] == ["landlord", "tenant"]
        assert [role["id"] for role in roles if role["suggested"]] == ["tenant"]

    def test_a_name_change_has_no_sides_to_ask_about(self):
        """Only two-sided cases get the question; everyone else is spared it."""

        assert resolve_filer_roles("illinois", court_code="cook:cd1", case_type_name="Name Change") == []
        assert "petition" in resolve_document_checklist(
            "illinois",
            court_code="cook:cd1",
            case_type_name="Name Change",
        )

    def test_category_guidance_for_a_case_type_with_no_checklist(self):
        checklist = resolve_document_checklist(
            "illinois",
            court_code="dupage",
            case_category_name="Small Claims",
            case_type_name="Contract - Debt Collection (Seller/Plaintiff) (Up to $2,500)",
        )

        assert list(checklist) == ["supporting_records", "proof_of_service", "fee_waiver"]


def test_each_side_of_a_case_gets_its_own_explanation():
    landlord = resolve_plan_guidance(
        "illinois",
        court_code="cook:cvd1",
        case_type_name="Eviction - Possession - Residential Complaint Filed - Non-Jury",
        filer_role="landlord",
    )
    tenant = resolve_plan_guidance(
        "illinois",
        court_code="cook:cvd1",
        case_type_name="Eviction - Possession - Residential Complaint Filed - Non-Jury",
        filer_role="tenant",
    )

    assert landlord["summary"] != tenant["summary"]
    assert landlord["learn_more_url"] != tenant["learn_more_url"]
    assert tenant["summary"].startswith("Your landlord")


def test_a_learn_more_link_has_to_be_a_web_address(tmp_path, monkeypatch):
    """A 'link' that runs script is not a link to a website."""
    (tmp_path / "base-case-types.yaml").write_text(yaml.safe_dump({}))
    (tmp_path / "states").mkdir(exist_ok=True)
    (tmp_path / "states" / "testland.yaml").write_text(
        yaml.safe_dump(
            {
                "case_types": {
                    "thing": {
                        "matches": {"names": ["Thing"]},
                        "about": {"summary": "About the thing.", "learn_more_url": "javascript:alert(1)"},
                        "documents": {"a_form": {"label": "A form", "requirement": "always"}},
                    }
                }
            }
        )
    )
    loader = JurisdictionConfigLoader(config_dir=tmp_path)
    monkeypatch.setattr("efile.services.document_checklists.config_loader", loader)

    guidance = resolve_plan_guidance("testland", case_type_name="Thing")

    assert guidance["summary"] == "About the thing."
    assert "learn_more_url" not in guidance


def test_a_case_type_with_nothing_written_about_it_has_no_narrative():
    assert resolve_plan_guidance("illinois", case_type_name="Nothing Configured") == {}
