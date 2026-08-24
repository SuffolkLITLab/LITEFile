#!/usr/bin/env python3
"""Download the official blank court forms used by the synthetic corpus."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_FILE = ROOT / "official_sources.json"
OUTPUT_DIR = ROOT / "official_templates"


def download(url: str, destination: Path) -> None:
    temporary = destination.with_suffix(".pdf.tmp")
    subprocess.run(
        [
            "curl",
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "5",
            "--retry-all-errors",
            "--retry-delay",
            "2",
            "--output",
            str(temporary),
            url,
        ],
        check=True,
    )
    if not temporary.read_bytes().startswith(b"%PDF-"):
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Expected a PDF from {url}")
    temporary.replace(destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "ids",
        nargs="*",
        help="Corpus IDs to download; omit to download all forms",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Download forms that already exist",
    )
    args = parser.parse_args()

    sources: dict[str, str] = json.loads(SOURCE_FILE.read_text())
    selected = args.ids or sorted(sources)
    unknown = sorted(set(selected) - set(sources))
    if unknown:
        parser.error(f"Unknown corpus IDs: {', '.join(unknown)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for form_id in selected:
        destination = OUTPUT_DIR / f"{form_id}.pdf"
        if destination.exists() and not args.force:
            print(f"skip {form_id}: {destination.relative_to(ROOT)} exists")
            continue
        print(f"download {form_id}: {sources[form_id]}")
        download(sources[form_id], destination)


if __name__ == "__main__":
    main()
