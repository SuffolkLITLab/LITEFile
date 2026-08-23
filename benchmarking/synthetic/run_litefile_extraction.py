#!/usr/bin/env python3
"""Run LITEFile's analyze_document() over the synthetic benchmark dataset.

From the LITEFile repository root:
  PYTHONPATH=efile_app DJANGO_SETTINGS_MODULE=efile.settings python benchmarking/synthetic/run_litefile_extraction.py

Requires the same OPENAI/API configuration as LITEFile. Results are emitted as JSONL on stdout.
"""

import json
from pathlib import Path

import django

django.setup()

from efile.services.document_extractions import analyze_document  # noqa: E402

ROOT = Path(__file__).resolve().parent

for line in (ROOT / "extractability.jsonl").read_text().splitlines():
    case = json.loads(line)
    for variant in ("interactive", "flattened"):
        pdf = ROOT / case[f"{variant}_pdf"]
        try:
            result = analyze_document(str(pdf), case["jurisdiction"])
            print(
                json.dumps(
                    {
                        "id": case["id"],
                        "variant": variant,
                        "pdf": str(pdf),
                        "result": result,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            print(
                json.dumps(
                    {
                        "id": case["id"],
                        "variant": variant,
                        "pdf": str(pdf),
                        "error": repr(e),
                    },
                    ensure_ascii=False,
                )
            )
