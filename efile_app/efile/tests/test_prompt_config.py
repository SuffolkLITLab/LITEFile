from efile.services.extraction_fields import COMMON_EXTRACTION_FIELDS, EXTRACTION_HINTS
from efile.utils.prompt_config import load_prompt, prompt_directory, render_prompt_messages


def test_document_extraction_prompt_catalog_has_production_and_candidate_versions():
    prompt = load_prompt("document_extraction")

    assert prompt["production_version"] == "v1"
    assert set(prompt["versions"]) >= {"v1", "v2"}
    assert prompt["versions"]["v1"]["preferred_model_tier"] == "small"
    assert prompt["versions"]["v2"]["status"] == "experimental"
    assert prompt["fields"]["form identifier"].startswith("The exact printed form number")
    assert "headers, footers" in prompt["versions"]["v2"]["templates"]["file_user"]


def test_default_prompt_catalog_is_bundled_inside_efile_package():
    assert prompt_directory().parent.name == "efile"
    assert prompt_directory().name == "prompts"
    assert (prompt_directory() / "document_extraction.yaml").is_file()


def test_extraction_fields_and_hints_come_from_prompt_catalog():
    prompt = load_prompt("document_evidence_extraction")

    assert COMMON_EXTRACTION_FIELDS == prompt["fields"]
    assert set(EXTRACTION_HINTS) == {"illinois", "massachusetts", "vermont", "default"}


def test_render_text_prompt_includes_fields_hint_and_document():
    messages, settings = render_prompt_messages(
        "document_extraction",
        mode="text",
        field_definitions={"court name": "Court shown on the filing"},
        jurisdiction_hint="Treat the division as the category.",
        document_text="Washington Unit, Civil Division",
        version="v2",
    )

    assert messages[0]["role"] == "system"
    assert "court name" in messages[1]["content"]
    assert "Treat the division as the category." in messages[1]["content"]
    assert "Washington Unit, Civil Division" in messages[1]["content"]
    assert settings["preferred_model_tier"] == "medium"


def test_production_text_fallback_preserves_the_baseline_without_jurisdiction_hint():
    messages, _settings = render_prompt_messages(
        "document_extraction",
        mode="text",
        field_definitions={"case type": "Specific case type"},
        jurisdiction_hint="This hint is used by the direct file prompt.",
        document_text="Motion",
        version="v1",
    )

    assert "This hint is used by the direct file prompt." not in str(messages)
    assert messages[1]["content"] == "Motion"


def test_staged_prompts_preserve_source_text_and_render_structured_candidates():
    evidence_prompt = load_prompt("document_evidence_extraction")
    taxonomy_prompt = load_prompt("efile_taxonomy_classification")

    assert "case type" not in evidence_prompt["fields"]
    assert {"form name", "form identifier", "form revision", "form purpose"} <= evidence_prompt["fields"].keys()
    assert taxonomy_prompt["workflow"]["order"] == ["court", "case_category", "case_type", "filing_type"]

    messages, _settings = render_prompt_messages(
        "efile_taxonomy_classification",
        mode="text",
        field_definitions={},
        document_text="COMPLAINT FOR DIVORCE UNDER G.L. c. 208, section 1B",
        template_values={
            "classification_level": "case type",
            "jurisdiction": "massachusetts",
            "court_name": "Middlesex Probate and Family Court",
            "filing_phase": "initial",
            "selected_case_category": {"code": "PFC", "name": "Probate and Family"},
            "selected_case_type": "not selected yet",
            "available_candidates": [{"code": "DIV", "name": "Divorce"}],
            "extracted_evidence": {"document title": "Complaint for Divorce"},
            "source_scope": "first 3 pages",
        },
    )

    rendered = messages[1]["content"]
    assert "code: DIV" in rendered
    assert "Middlesex Probate and Family Court" in rendered
    assert "COMPLAINT FOR DIVORCE" in rendered
    assert "not as a replacement" in rendered


def test_structured_prompt_values_do_not_wrap_authoritative_candidate_names():
    candidate_name = "Contract - Other (Excluding Business/Employment Dispute and Debt Collection) ($2,500.01 to $10K)"
    messages, _settings = render_prompt_messages(
        "efile_taxonomy_classification",
        mode="text",
        field_definitions={},
        document_text="Small Claims Complaint",
        template_values={
            "classification_level": "case type",
            "jurisdiction": "illinois",
            "court_name": "Kane County Circuit Court",
            "filing_phase": "initial",
            "selected_case_category": {"code": "7421", "name": "Small Claims"},
            "selected_case_type": "not selected yet",
            "available_candidates": [{"code": "164987", "name": candidate_name}],
            "extracted_evidence": {},
            "source_scope": "first 3 pages",
        },
    )

    assert candidate_name in messages[1]["content"]
