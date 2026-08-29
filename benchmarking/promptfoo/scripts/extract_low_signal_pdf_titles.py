#!/usr/bin/env python3
"""Recover usable form titles from visible PDF text, not crawl metadata."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[3]
FORMS_ROOT = ROOT / "court_forms"
DEFAULT_REPORT = (
    ROOT
    / "benchmarking/promptfoo/lab-notebook/reviews/2026-08-27-crosswalk-field-review-tool/artifacts/text-derived-titles.json"
)
LOW_SIGNAL_TITLES = {
    "(untitled)",
    "view form",
    "layout 1",
    "kreyòl ayisyen",
    "português, portugal",
    "tiếng việt",
}
TITLE_WORDS = re.compile(
    r"\b(?:application|affidavit|agreement|answer|certificate|complaint|consent|"
    r"declaration|motion|notice|order|petition|request|statement|summons|voucher|"
    r"waiver|form|report|information|certification|authorization|admission)\b",
    re.IGNORECASE,
)
BOILERPLATE = re.compile(
    r"(?:please wait|full contents of this document|adobe reader|for further support)",
    re.IGNORECASE,
)
LOW_QUALITY_HEADING = re.compile(
    r"(?:this form is for reference|^voucher total$|^application form$|^complaint$|"
    r"^summons$|^certificate of the court$|^certificate of services(?: page \d+)?$|"
    r"^general information|^filing instructions|^annual certification of$)",
    re.IGNORECASE,
)


def extract_text(path: Path) -> tuple[str, str]:
    """Use embedded text first, then pdftotext for parser-specific PDFs."""
    try:
        reader = PdfReader(path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:2])
        if len(text.strip()) >= 80 and not BOILERPLATE.search(text):
            return text, "pypdf"
    except Exception:
        text = ""
    result = subprocess.run(
        ["pdftotext", str(path), "-"], capture_output=True, check=False
    )
    fallback = (
        result.stdout.decode("utf-8", errors="ignore") if result.returncode == 0 else ""
    )
    if len(fallback.strip()) > len(text.strip()) and not BOILERPLATE.search(fallback):
        return fallback, "pdftotext"
    return text, "unusable_text"


def lines_from_text(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip(" -–—_:;")
        for line in text.splitlines()
        if line.strip()
    ]


def uppercase_ratio(value: str) -> float:
    letters = [character for character in value if character.isalpha()]
    return (
        sum(character.isupper() for character in letters) / len(letters)
        if letters
        else 0.0
    )


def title_from_text(text: str) -> tuple[str | None, float]:
    """Return a conservative first-page heading candidate and confidence."""
    candidates: list[tuple[float, str]] = []
    for index, line in enumerate(lines_from_text(text)[:35]):
        if not 6 <= len(line) <= 170 or BOILERPLATE.search(line):
            continue
        letters = sum(character.isalpha() for character in line)
        if letters < 5:
            continue
        upper = uppercase_ratio(line)
        keyword = bool(TITLE_WORDS.search(line))
        # A title normally occurs near the top, is visually prominent, and
        # includes a form-document noun. Do not treat institutional headers as
        # title evidence by themselves.
        score = (0.35 if keyword else 0) + min(upper, 0.5) + max(0, 0.2 - index * 0.012)
        if keyword and score >= 0.62:
            candidates.append((score, line))
    if not candidates:
        return None, 0.0
    score, title = max(candidates, key=lambda item: item[0])
    if LOW_QUALITY_HEADING.search(title) or title.rstrip().endswith(" OF"):
        return None, 0.0
    return title, round(min(score, 0.99), 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write high-confidence titles to form_registry.json",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    registry_path = FORMS_ROOT / "form_registry.json"
    rows = json.loads(registry_path.read_text(encoding="utf-8"))
    results = []
    updates = 0
    for row in rows:
        original_title = str(
            row.get("canonical_title") or row.get("title") or ""
        ).strip()
        if original_title.casefold() not in LOW_SIGNAL_TITLES:
            continue
        relative_path = str(row.get("relative_path") or row.get("filename") or "")
        text, method = extract_text(FORMS_ROOT / relative_path)
        title, confidence = title_from_text(text)
        accepted = bool(title and confidence >= 0.72)
        results.append(
            {
                "path": relative_path,
                "crawl_title": original_title,
                "extracted_title": title,
                "confidence": confidence,
                "extraction_method": method,
                "accepted": accepted,
            }
        )
        if args.apply and accepted:
            row["crawl_title"] = original_title
            row["canonical_title"] = title
            row["title_source"] = f"pdf_text:{method}"
            updates += 1

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.apply:
        registry_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        f"Recovered {sum(item['accepted'] for item in results)} of {len(results)} low-signal titles; applied {updates}"
    )


if __name__ == "__main__":
    main()
