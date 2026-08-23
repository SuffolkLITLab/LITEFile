"""Render source/evidence ablations for hierarchical taxonomy classification."""

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "efile_app"))

from efile.utils.prompt_config import render_prompt_messages  # noqa: E402


def _render(context, *, include_evidence, include_source):
    variables = context["vars"]
    evidence = (
        variables["extracted_evidence"]
        if include_evidence
        else "Not supplied in this ablation."
    )
    document_text = (
        variables["document_text"]
        if include_source
        else "Not supplied in this ablation."
    )
    source_scope = variables["source_scope"] if include_source else "not supplied"
    messages, _settings = render_prompt_messages(
        "efile_taxonomy_classification",
        mode="text",
        field_definitions={},
        document_text=document_text,
        version="v1",
        template_values={
            "classification_level": variables["classification_level"],
            "jurisdiction": variables["jurisdiction"],
            "court_name": variables["court_name"],
            "filing_phase": variables["filing_phase"],
            "selected_case_category": variables.get("selected_case_category")
            or "not selected yet",
            "selected_case_type": variables.get("selected_case_type")
            or "not selected yet",
            "available_candidates": variables["available_candidates"],
            "extracted_evidence": evidence,
            "source_scope": source_scope,
        },
    )
    return json.dumps(messages, ensure_ascii=False)


def create_source_only(context):
    return _render(context, include_evidence=False, include_source=True)


def create_evidence_only(context):
    return _render(context, include_evidence=True, include_source=False)


def create_evidence_and_source(context):
    return _render(context, include_evidence=True, include_source=True)
