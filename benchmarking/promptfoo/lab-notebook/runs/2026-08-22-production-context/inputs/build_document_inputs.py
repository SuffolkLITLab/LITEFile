#!/usr/bin/env python3
"""Precompute production-like PDF text and AcroForm field context."""

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from markitdown import MarkItDown
from pypdf import PdfReader
from pypdf.generic import ArrayObject, BooleanObject, DictionaryObject, IndirectObject

PROMPTFOO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROMPTFOO_ROOT / "data" / "document_inputs.json"
CASE_PATHS = [
    PROMPTFOO_ROOT / "data" / "cases.jsonl",
    PROMPTFOO_ROOT / "data" / "sentinel_cases.jsonl",
]


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def resolve_file_uri(uri):
    if not uri.startswith("file://"):
        raise ValueError(f"Expected file URI, got {uri!r}")
    return (PROMPTFOO_ROOT / uri.removeprefix("file://")).resolve()


def json_value(value):
    if isinstance(value, IndirectObject):
        return json_value(value.get_object())
    if isinstance(value, ArrayObject | list | tuple):
        return [json_value(item) for item in value]
    if isinstance(value, DictionaryObject | dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, BooleanObject | bool):
        return bool(value)
    if value is None or isinstance(value, str | int | float):
        return value
    return str(value)


def has_selected_value(value):
    if value in (None, "", False, "/Off", "Off"):
        return False
    if isinstance(value, list):
        return any(has_selected_value(item) for item in value)
    return True


def extract_pdf_fields(path):
    fields = PdfReader(path).get_fields() or {}
    extracted = []
    for name, definition in fields.items():
        value = json_value(definition.get("/V"))
        if not has_selected_value(value):
            continue
        extracted.append(
            {
                "name": str(name),
                "alternate_name": json_value(definition.get("/TU")),
                "mapping_name": json_value(definition.get("/TM")),
                "field_type": json_value(definition.get("/FT")),
                "value": value,
            }
        )
    return extracted


def build_document_inputs():
    cases = [case for path in CASE_PATHS for case in read_jsonl(path)]
    documents = {}
    converter = MarkItDown()
    for case in cases:
        input_id = case["vars"]["document_input_id"]
        if input_id in documents:
            continue
        source_uri = case["vars"]["document"]
        path = resolve_file_uri(source_uri)
        documents[input_id] = {
            "source_pdf": source_uri,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "markitdown_text": converter.convert(path).text_content,
            "pdf_fields": extract_pdf_fields(path),
        }
    return {
        "schema_version": 1,
        "tools": {
            "markitdown": version("markitdown"),
            "pdfminer-six": version("pdfminer-six"),
            "pypdf": version("pypdf"),
        },
        "documents": documents,
    }


def render_document_inputs():
    return json.dumps(build_document_inputs(), ensure_ascii=False, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Fail if document_inputs.json is stale"
    )
    args = parser.parse_args()
    rendered = render_document_inputs()
    if args.check:
        existing = (
            OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        )
        if existing != rendered:
            raise SystemExit(
                "promptfoo/data/document_inputs.json is stale; run npm run build-inputs"
            )
        return
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    count = len(json.loads(rendered)["documents"])
    print(f"Wrote {count} preprocessed document inputs to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
