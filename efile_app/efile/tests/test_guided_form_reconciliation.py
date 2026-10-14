"""Safety tests for importing source-identified guided-interview forms."""

import copy
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "benchmarking/promptfoo/scripts/reconcile_guided_interview_forms.py"
SPEC = importlib.util.spec_from_file_location("guided_form_reconciliation", SCRIPT)
assert SPEC and SPEC.loader
RECONCILER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECONCILER)
reconcile = vars(RECONCILER)["reconcile"]
search_aliases = vars(RECONCILER)["search_aliases"]


def registry(entries=None):
    return {"updated_at": "old", "registry": copy.deepcopy(entries or [])}


def source_entry(state, canonical_id, form_id, canonical_name, aliases=None):
    return {
        "form": {
            "canonical_id": canonical_id,
            "jurisdiction": state,
            "form_id": form_id,
            "form_id_aliases": [],
            "canonical_name": canonical_name,
            "aliases": list(aliases or []),
            "official": False,
            "is_form": True,
            "is_efileable": None,
            "document_role": "court_form",
            "source_urls": ["https://github.com/example/repo/blob/abc/form.pdf"],
        },
        "mappings": [],
    }


def document(
    output_id,
    *,
    state="illinois",
    title="Motion to Seal Eviction Record",
    printed_title=None,
    form_id="ATJ 503.11",
    output_kind="document",
    stage="subsequent",
):
    return {
        "id": output_id,
        "repo": f"IllinoisLegalAidOnline/docassemble-{output_id.split(':')[0]}",
        "title": title,
        "printed_title": printed_title,
        "form_id": form_id,
        "source_urls": ["https://github.com/example/repo/blob/abc/form.pdf"],
        "template_paths": ["docassemble/example/data/templates/form.pdf"],
        "filing_status": "court_filing",
        "output_kind": output_kind,
        "stage": stage,
    }


def manifest(state, *docs):
    return {"state": state, "documents": list(docs)}


def test_generic_motion_and_order_labels_never_create_mappings():
    docs = [
        document("Motion:motion", title="Motion", printed_title="MOTION"),
        document("Order:order", title="Order", printed_title="ORDER", form_id="ATJ 800.10"),
    ]
    labels = {
        "illinois": {
            "motion": {"subsequent": [{"label": "Motion", "court": "cook:cv", "code": "1"}]},
            "order": {"initial": [{"label": "Order", "court": "cook:cv", "code": "2"}]},
        }
    }

    result = registry()
    reconcile(result, [manifest("illinois", *docs)], labels, "2026-10-13")

    assert len(result["registry"]) == 2
    assert all(entry["mappings"] == [] for entry in result["registry"])


def test_composite_bundles_and_page_fragments_are_excluded_from_identity_and_mapping_import():
    bundle = document("Eviction:all_forms", title="All forms", output_kind="bundle")
    fragment = document(
        "VacateDefaultForeclosure:motion_part_2", title="Motion to Vacate Foreclosure", output_kind="fragment"
    )
    result = registry()

    changes = reconcile(
        result,
        [manifest("illinois", bundle, fragment)],
        {
            "illinois": {
                "all forms": {"subsequent": [{"label": "All Forms"}]},
                "motion to vacate foreclosure": {"subsequent": [{"label": "Motion to Vacate Foreclosure"}]},
            }
        },
        "2026-10-13",
    )

    assert result["registry"] == []
    assert changes == []


def test_same_printed_id_is_separated_by_state():
    il = document("Appearance:appearance", title="Appearance", printed_title="APPEARANCE", state="illinois")
    vt = document("Appearance:appearance", title="Appearance", printed_title="APPEARANCE", state="vermont")
    result = registry()

    reconcile(result, [manifest("illinois", il), manifest("vermont", vt)], {}, "2026-10-13")

    assert {(e["form"]["jurisdiction"], e["form"]["form_id"]) for e in result["registry"]} == {
        ("illinois", "ATJ 503.11"),
        ("vermont", "ATJ 503.11"),
    }
    assert len({e["form"]["canonical_id"] for e in result["registry"]}) == 2


def test_repeated_printed_id_reuses_identity_and_is_idempotent():
    first = document("Appearance:one", title="Appearance", printed_title="APPEARANCE")
    second = document("Appearance:two", title="Appearance (e-file)", printed_title="APPEARANCE")
    result = registry()

    first_changes = reconcile(result, [manifest("illinois", first, second)], {}, "2026-10-13")
    before = copy.deepcopy(result)
    second_changes = reconcile(result, [manifest("illinois", first, second)], {}, "2026-10-13")

    assert len(result["registry"]) == 1
    form = result["registry"][0]["form"]
    assert set(form["guided_interview_outputs"]) == {"Appearance:one", "Appearance:two"}
    assert "Appearance (e-file)" in form["aliases"]
    assert len(first_changes) == 1
    assert second_changes == []
    assert result == before


def test_unknown_evictor_title_does_not_map_to_generic_motion_or_sealing_label():
    source = document(
        "RemoveEvictionFromPublicRecord:motion",
        title="Motion to Seal Eviction Record",
        printed_title="PETITION TO REMOVE EVICTION COURT FILE FROM PUBLIC RECORD",
        form_id="ATJ 000.00",
    )
    labels = {
        "illinois": {
            "motion": {"subsequent": [{"label": "Motion", "court": "dupage:cv", "code": "10"}]},
        }
    }
    result = registry()

    reconcile(result, [manifest("illinois", source)], labels, "2026-10-13")

    assert result["registry"][0]["mappings"] == []


def test_printed_id_aliases_preserve_exact_label_stage_and_source_scope():
    source = document("FinancialAffidavit:primary", printed_title="Financial Affidavit", form_id="ATJ 251.5")
    source["case_categories"] = ["Family"]
    labels = {
        "illinois": {
            "financial affidavit": {
                "initial": [{"label": "Financial Affidavit"}],
                "subsequent": [{"label": "Financial Affidavit"}],
            }
        }
    }
    aliases = search_aliases([manifest("illinois", source)], labels, "2026-10-13")
    assert aliases["concepts"]["guided_il_atj2515"]["terms"] == ["ATJ 251.5"]
    assert aliases["concepts"]["guided_il_atj2515"]["path_only"] is True
    assert len(aliases["path_aliases"]) == 1
    assert aliases["path_aliases"][0]["initial"] is False
    assert aliases["path_aliases"][0]["filing_type"] == ["Financial Affidavit"]
    assert aliases["path_aliases"][0]["case_category"] == ["Family"]


def test_court_specific_and_split_outputs_do_not_generate_statewide_aliases():
    source = document("CookCounty:primary", printed_title="Financial Affidavit")
    fragment = document("FinancialAffidavit:part", printed_title="Financial Affidavit", output_kind="fragment")
    labels = {"illinois": {"financial affidavit": {"subsequent": [{"label": "Financial Affidavit"}]}}}
    aliases = search_aliases([manifest("illinois", source, fragment)], labels, "2026-10-13")
    assert aliases["concepts"] == {}
    assert aliases["path_aliases"] == []


def test_cook_only_ccdr_form_does_not_create_statewide_mapping_or_search_alias():
    source = document(
        "JointSimplifiedDivorce:joint_simplified_divorce_petition",
        title="Joint Petition for Simplified Dissolution forms",
        printed_title="JOINT PETITION FOR SIMPLIFIED DISSOLUTION",
        form_id="CCDR 0019 A",
        stage="initial",
    )
    source["repo"] = "IllinoisLegalAidOnline/docassemble-JointSimplifiedDivorce"
    source["source_urls"] = ["https://www.illinoislegalaid.org/legal-information/joint-simplified-divorce-cook-county"]
    labels = {
        "illinois": {
            "joint petition for simplified dissolution": {
                "initial": [{"label": "Joint Petition for Simplified Dissolution"}]
            }
        }
    }

    result = registry()
    reconcile(result, [manifest("illinois", source)], labels, "2026-10-13")
    aliases = search_aliases([manifest("illinois", source)], labels, "2026-10-13")

    assert result["registry"][0]["mappings"] == []
    assert aliases["concepts"] == {}
    assert aliases["path_aliases"] == []


def test_cook_source_removes_its_prior_unscoped_exact_title_suggestion():
    source = document(
        "JointSimplifiedDivorce:joint_simplified_divorce_petition",
        printed_title="JOINT PETITION FOR SIMPLIFIED DISSOLUTION",
        form_id="CCDR 0019 A",
        stage="initial",
    )
    source["repo"] = "IllinoisLegalAidOnline/docassemble-JointSimplifiedDivorce"
    source["source_urls"] = ["https://www.illinoislegalaid.org/legal-information/joint-simplified-divorce-cook-county"]
    form = source_entry("illinois", "IL-CCDR", "CCDR 0019 A", source["printed_title"])
    form["mappings"] = [
        {
            "filing_type": source["printed_title"],
            "court_scope": {"observed_route_keys": []},
            "notes": f"Exact title suggestion. Output: {source['id']}.",
        }
    ]
    result = registry([form])
    labels = {
        "illinois": {
            "joint petition for simplified dissolution": {
                "initial": [{"label": "JOINT PETITION FOR SIMPLIFIED DISSOLUTION"}]
            }
        }
    }

    changes = reconcile(result, [manifest("illinois", source)], labels, "2026-10-13")

    assert result["registry"][0]["mappings"] == []
    assert any(change["status"] == "removed_unscoped_court_limited_mapping" for change in changes)


def test_shared_cook_mapping_is_order_independent_and_idempotent():
    cook = document(
        "EmergencyOrderOfProtectionCookCounty:plenary_op",
        title="Plenary Order of Protection (draft)",
        printed_title="ORDER OF PROTECTION",
        form_id="ATJ 405.4",
        stage="initial",
    )
    cook["repo"] = "IllinoisLegalAidOnline/docassemble-EmergencyOrderOfProtectionCookCounty"
    statewide = document(
        "OrderOfProtection:plenary_op",
        title="Plenary Order of Protection (draft)",
        printed_title="ORDER OF PROTECTION",
        form_id="ATJ 405.4",
        stage="initial",
    )
    statewide["repo"] = "IllinoisLegalAidOnline/docassemble-OrderOfProtection"
    statewide["source_urls"] = [
        "https://github.com/IllinoisLegalAidOnline/docassemble-OrderOfProtection/blob/abc/plenary_op.pdf"
    ]
    form = source_entry("illinois", "IL-ATJ4054", "ATJ 405.4", "ORDER OF PROTECTION")
    form["mappings"] = [
        {
            "filing_type": "Order of Protection",
            "court_scope": {"observed_route_keys": []},
            "notes": f"Old generated mapping. Output: {cook['id']}.",
        }
    ]
    labels = {"illinois": {"order of protection": {"initial": [{"label": "Order of Protection"}]}}}

    results = []
    for docs in ([cook, statewide], [statewide, cook]):
        result = registry([form])
        changes = reconcile(result, [manifest("illinois", *docs)], labels, "2026-10-13")
        stable = copy.deepcopy(result)
        second_changes = reconcile(result, [manifest("illinois", *reversed(docs))], labels, "2026-10-13")

        assert result == stable
        assert second_changes == []
        assert len(result["registry"][0]["mappings"]) == 1
        assert "OrderOfProtection:plenary_op" in result["registry"][0]["mappings"][0]["notes"]
        assert "EmergencyOrderOfProtectionCookCounty:plenary_op" not in result["registry"][0]["mappings"][0]["notes"]
        results.append((result, changes))

    assert results[0] == results[1]


def test_reviewed_ccdr_label_without_observed_cook_route_is_not_applied():
    form = source_entry("illinois", "IL-CCDR", "CCDR 0019 A", "Joint petition")
    result = registry([form])
    evidence = {
        "state": "illinois",
        "checked_at": "2026-10-13",
        "records": [
            {
                "form_ids": ["CCDR 0019 A"],
                "source_document_title": "Joint Petition for Simplified Dissolution",
                "exact_filing_type": "Joint Petition for Simplified Dissolution",
                "case_category": "Family",
                "case_types": [],
                "mapping_status": "verified_label",
                "source_urls": ["https://www.example.test/cook-county"],
                "available_stages": ["initial"],
            }
        ],
    }
    apply_reviewed = vars(RECONCILER)["apply_reviewed_associations"]

    assert apply_reviewed(result, evidence) == []
    assert result["registry"][0]["mappings"] == []
    aliases = {"concepts": {}, "definitions": {}, "path_aliases": []}
    vars(RECONCILER)["add_reviewed_search_aliases"](aliases, evidence)
    assert aliases["concepts"] == {}
    assert aliases["path_aliases"] == []


def test_reviewed_ccdr_label_rejects_non_cook_or_mixed_route_scope():
    for route_codes in (["dupage"], ["cook:dr1", "lake"]):
        form = source_entry("illinois", "IL-CCDR", "CCDR 0019 A", "Joint petition")
        result = registry([form])
        evidence = {
            "state": "illinois",
            "checked_at": "2026-10-13",
            "records": [
                {
                    "form_ids": ["CCDR 0019 A"],
                    "source_document_title": "Joint Petition for Simplified Dissolution",
                    "exact_filing_type": "Joint Petition for Simplified Dissolution",
                    "case_category": "Family",
                    "case_types": [],
                    "mapping_status": "verified_label",
                    "source_urls": ["https://www.example.test/cook-county"],
                    "available_stages": ["initial"],
                    "court_codes": route_codes,
                }
            ],
        }
        apply_reviewed = vars(RECONCILER)["apply_reviewed_associations"]

        assert apply_reviewed(result, evidence) == []
        assert result["registry"][0]["mappings"] == []


def test_reviewed_ccdr_alias_keeps_explicit_all_cook_route_scope():
    evidence = {
        "state": "illinois",
        "checked_at": "2026-10-13",
        "records": [
            {
                "form_ids": ["CCDR 0019 A"],
                "source_document_title": "Joint Petition for Simplified Dissolution",
                "exact_filing_type": "Joint Petition for Simplified Dissolution",
                "case_category": "Family",
                "case_types": [],
                "mapping_status": "verified_label",
                "source_urls": ["https://www.example.test/cook-county"],
                "available_stages": ["initial"],
                "court_codes": ["cook:dr1", "cook:dr2"],
            }
        ],
    }
    aliases = {"concepts": {}, "definitions": {}, "path_aliases": []}

    vars(RECONCILER)["add_reviewed_search_aliases"](aliases, evidence)

    assert aliases["path_aliases"][0]["court_codes"] == ["cook:dr1", "cook:dr2"]


def test_distinct_titles_sharing_a_template_have_distinct_canonical_ids():
    first = document("Motion:primary", printed_title="Motion to Continue", form_id=None)
    second = document("Motion:order", printed_title="Order on Motion to Continue", form_id=None)
    result = registry()
    reconcile(result, [manifest("illinois", first, second)], {}, "2026-10-13")
    assert len({entry["form"]["canonical_id"] for entry in result["registry"]}) == 2


def test_generic_ui_title_does_not_become_alias_for_a_specific_printed_title():
    source = document(
        "EvictATenant:notice_nonpayment",
        title="Notice",
        printed_title="NOTICE OF TERMINATION FOR NON-PAYMENT OF RENT",
        form_id="TR 3505.2",
    )
    result = registry()

    reconcile(result, [manifest("illinois", source)], {}, "2026-10-13")

    form = result["registry"][0]["form"]
    assert form["canonical_name"] == "NOTICE OF TERMINATION FOR NON-PAYMENT OF RENT"
    assert "Notice" not in form["aliases"]


def test_known_non_efileable_form_does_not_gain_an_observed_label_mapping():
    form = source_entry("illinois", "IL-paper", "ATJ 503.11", "Appearance")
    form["form"]["is_efileable"] = False
    result = registry([form])
    source = document("Appearance:primary", printed_title="Appearance")
    labels = {"illinois": {"appearance": {"subsequent": [{"label": "Appearance"}]}}}
    reconcile(result, [manifest("illinois", source)], labels, "2026-10-13")
    assert result["registry"][0]["mappings"] == []


def test_reviewed_specific_form_label_replaces_broad_historical_alternatives():
    form = source_entry("vermont", "VT-813B", "400-00813B", "Financial affidavit")
    form["mappings"] = [{"filing_type": "813A Financial Affidavit"}]
    result = registry([form])
    evidence = {
        "state": "vermont",
        "checked_at": "2026-10-13",
        "records": [
            {
                "form_ids": ["400-00813B"],
                "exact_filing_type": "813B Financial Affidavit",
                "case_category": "Family",
                "case_types": [],
                "mapping_status": "verified_label",
                "reason": "Reviewed printed form and exact observed provider label.",
                "source_urls": ["https://www.vtcourts.gov/example.pdf"],
            }
        ],
    }
    apply_reviewed = vars(RECONCILER)["apply_reviewed_associations"]
    apply_reviewed(result, evidence)
    mappings = result["registry"][0]["mappings"]
    assert [mapping["filing_type"] for mapping in mappings] == ["813B Financial Affidavit"]
    assert mappings[0]["catalog_status"] == "partial_observation"
    assert mappings[0]["association_status"] == "unverified_suggestion"
    assert mappings[0]["human_verification"]["verified"] is False
    assert apply_reviewed(result, evidence) == []


def test_reviewed_association_replacement_preserves_audited_initial_filing_mapping():
    form = source_entry("vermont", "VT-RFA", "400-00150C", "RFA complaint")
    initial = {
        "filing_type": "Initial Filing",
        "filing_phase": "initial",
        "association_status": "unverified_suggestion",
        "notes": "Separate audited initial-filing association.",
    }
    form["mappings"] = [initial, {"filing_type": "old broad alternative"}]
    result = registry([form])
    evidence = {
        "state": "vermont",
        "checked_at": "2026-10-13",
        "records": [
            {
                "form_ids": ["400-00150C"],
                "exact_filing_type": "Affidavit",
                "case_category": "Family",
                "case_types": [],
                "stage_constraint": "subsequent (source interview stage)",
                "available_stages": ["initial", "subsequent"],
                "mapping_status": "verified_label",
                "reason": "Reviewed subsequent label.",
                "source_urls": ["https://www.vtcourts.gov/example.pdf"],
            }
        ],
    }
    apply_reviewed = vars(RECONCILER)["apply_reviewed_associations"]

    apply_reviewed(result, evidence)

    assert [mapping["filing_type"] for mapping in result["registry"][0]["mappings"]] == [
        "Initial Filing",
        "Affidavit",
    ]
    assert result["registry"][0]["mappings"][0] == initial
