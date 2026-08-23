"""Render the shared production prompt catalog for Promptfoo."""

import json
import sys
from functools import cache
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "efile_app"))

from efile.utils.prompt_config import load_prompt, render_prompt_messages  # noqa: E402

DOCUMENT_INPUTS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "document_inputs.json"
)


@cache
def _document_inputs():
    return json.loads(DOCUMENT_INPUTS_PATH.read_text(encoding="utf-8"))["documents"]


def _preprocessed_context(variables, include_fields):
    document = _document_inputs()[variables["document_input_id"]]
    sections = ["MarkItDown text:\n" + document["markitdown_text"]]
    if include_fields:
        fields = document["pdf_fields"]
        sections.append(
            "Extracted PDF form field values:\n"
            + (json.dumps(fields, ensure_ascii=False, indent=2) if fields else "[]")
        )
    return "\n\n".join(sections)


def _create_prompt(context, version):
    variables = context["vars"]
    definition = load_prompt("document_extraction")
    messages, _settings = render_prompt_messages(
        "document_extraction",
        mode="text",
        field_definitions=dict(definition["fields"]),
        jurisdiction_hint=definition["jurisdiction_hints"].get(
            variables["jurisdiction"], definition["jurisdiction_hints"]["default"]
        ),
        document_text=variables["document"],
        version=version,
    )
    return json.dumps(messages, ensure_ascii=False)


def _create_vision_prompt(context, version):
    variables = context["vars"]
    definition = load_prompt("document_extraction")
    messages, _settings = render_prompt_messages(
        "document_extraction",
        mode="file",
        field_definitions=dict(definition["fields"]),
        jurisdiction_hint=definition["jurisdiction_hints"].get(
            variables["jurisdiction"], definition["jurisdiction_hints"]["default"]
        ),
        version=version,
    )
    messages[1]["content"] = [
        {"type": "text", "text": messages[1]["content"]},
        {
            "type": "image_url",
            "image_url": {"url": variables["document_image"], "detail": "high"},
        },
    ]
    return json.dumps(messages, ensure_ascii=False)


def _create_preprocessed_prompt(context, version, include_fields):
    variables = context["vars"]
    definition = load_prompt("document_extraction")
    messages, _settings = render_prompt_messages(
        "document_extraction",
        mode="text",
        field_definitions=dict(definition["fields"]),
        jurisdiction_hint=definition["jurisdiction_hints"].get(
            variables["jurisdiction"], definition["jurisdiction_hints"]["default"]
        ),
        document_text=_preprocessed_context(variables, include_fields),
        version=version,
    )
    return json.dumps(messages, ensure_ascii=False)


def _create_vision_context_prompt(context, version):
    variables = context["vars"]
    definition = load_prompt("document_extraction")
    messages, _settings = render_prompt_messages(
        "document_extraction",
        mode="file",
        field_definitions=dict(definition["fields"]),
        jurisdiction_hint=definition["jurisdiction_hints"].get(
            variables["jurisdiction"], definition["jurisdiction_hints"]["default"]
        ),
        version=version,
    )
    messages[1]["content"] = [
        {
            "type": "text",
            "text": messages[1]["content"]
            + "\n\nMachine-readable context extracted before the model call:\n"
            + _preprocessed_context(variables, include_fields=True),
        },
        {
            "type": "image_url",
            "image_url": {"url": variables["document_image"], "detail": "high"},
        },
    ]
    return json.dumps(messages, ensure_ascii=False)


def create_v1(context):
    return _create_prompt(context, "v1")


def create_v2(context):
    return _create_prompt(context, "v2")


def create_v1_vision(context):
    return _create_vision_prompt(context, "v1")


def create_v2_vision(context):
    return _create_vision_prompt(context, "v2")


def create_v1_markitdown(context):
    return _create_preprocessed_prompt(context, "v1", include_fields=False)


def create_v2_markitdown(context):
    return _create_preprocessed_prompt(context, "v2", include_fields=False)


def create_v1_markitdown_fields(context):
    return _create_preprocessed_prompt(context, "v1", include_fields=True)


def create_v2_markitdown_fields(context):
    return _create_preprocessed_prompt(context, "v2", include_fields=True)


def create_v1_vision_context(context):
    return _create_vision_context_prompt(context, "v1")


def create_v2_vision_context(context):
    return _create_vision_context_prompt(context, "v2")
