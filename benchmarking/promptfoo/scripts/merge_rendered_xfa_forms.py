#!/usr/bin/env python3
"""Merge verified visual XFA conversions into the local form registry.

The converted PDFs are image-only, so pypdf text extraction cannot distinguish
a real rendered form from a rendered Adobe placeholder. This script OCRs page
one, records the evidence, and switches ``rendered_visual_path`` only when the
conversion contains real document content.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from extract_low_signal_pdf_titles import LOW_SIGNAL_TITLES, title_from_text

ROOT = Path(__file__).resolve().parents[3]
FORMS_ROOT = ROOT / "court_forms"
DEFAULT_REPORT = (
    ROOT
    / "benchmarking/promptfoo/lab-notebook/reviews/2026-08-27-crosswalk-field-review-tool/artifacts/rendered-xfa-merge.json"
)
PLACEHOLDER_TEXT = ("please wait", "full contents of this document", "adobe reader")


def ocr_first_page(path: Path) -> str:
    """Render then OCR one page of an image-only converted PDF."""
    with tempfile.TemporaryDirectory(prefix="litefile-xfa-") as temporary:
        image_path = Path(temporary) / "page.png"
        render = subprocess.run(
            [
                "mutool",
                "draw",
                "-F",
                "png",
                "-r",
                "180",
                "-o",
                str(image_path),
                str(path),
            ],
            capture_output=True,
            check=False,
        )
        if render.returncode:
            return ""
        ocr = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", "eng"],
            capture_output=True,
            check=False,
        )
        return ocr.stdout.decode("utf-8", errors="ignore") if not ocr.returncode else ""


def is_real_content(text: str) -> bool:
    normalized = text.casefold()
    return len(text.strip()) >= 100 and not any(
        marker in normalized for marker in PLACEHOLDER_TEXT
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    registry_path = FORMS_ROOT / "form_registry.json"
    rows = json.loads(registry_path.read_text(encoding="utf-8"))
    results = []
    merged = 0
    titles_recovered = 0
    for row in rows:
        relative_path = str(row.get("relative_path") or row.get("filename") or "")
        original_path = FORMS_ROOT / relative_path
        converted_path = (
            original_path.parent / "rendered_visual_forms" / original_path.name
        )
        if not converted_path.is_file():
            continue
        text = ocr_first_page(converted_path)
        usable = is_real_content(text)
        title, confidence = title_from_text(text) if usable else (None, 0.0)
        original_title = str(
            row.get("canonical_title") or row.get("title") or ""
        ).strip()
        title_accepted = bool(
            original_title.casefold() in LOW_SIGNAL_TITLES
            and title
            and confidence >= 0.72
        )
        results.append(
            {
                "path": relative_path,
                "converted_path": converted_path.relative_to(FORMS_ROOT).as_posix(),
                "ocr_characters": len(text.strip()),
                "usable_rendered_content": usable,
                "extracted_title": title,
                "title_confidence": confidence,
                "title_accepted": title_accepted,
            }
        )
        if args.apply and usable:
            row["rendered_visual_path"] = converted_path.relative_to(
                FORMS_ROOT
            ).as_posix()
            row["rendered_content_verification"] = "ocr_first_page"
            merged += 1
            if title_accepted:
                row["crawl_title"] = original_title
                row["canonical_title"] = title
                row["title_source"] = "rendered_xfa_ocr"
                titles_recovered += 1

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.apply:
        registry_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        f"Verified {sum(item['usable_rendered_content'] for item in results)} of {len(results)} rendered PDFs; "
        f"merged {merged}; recovered {titles_recovered} titles"
    )


if __name__ == "__main__":
    main()
