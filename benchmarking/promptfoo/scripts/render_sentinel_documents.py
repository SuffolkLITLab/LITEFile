#!/usr/bin/env python3
"""Render sentinel PDFs to page images and create one raster-only scan."""

import json
import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter

PROMPTFOO_ROOT = Path(__file__).resolve().parents[1]
SENTINEL_PATH = PROMPTFOO_ROOT / "data" / "sentinel_cases.jsonl"
IMAGE_DIR = PROMPTFOO_ROOT / ".generated" / "sentinel_images"
DOCUMENT_DIR = PROMPTFOO_ROOT / ".generated" / "sentinel_documents"


def resolve_file_uri(uri):
    if not uri.startswith("file://"):
        raise ValueError(f"Expected file URI, got {uri!r}")
    return (PROMPTFOO_ROOT / uri.removeprefix("file://")).resolve()


def run(*args):
    subprocess.run(args, check=True)


def canonicalize_pdf(source, destination):
    reader = PdfReader(source)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.metadata = None
    writer._ID = None
    with destination.open("wb") as output:
        writer.write(output)


def main():
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    cases = [
        json.loads(line)
        for line in SENTINEL_PATH.read_text(encoding="utf-8").splitlines()
    ]

    for case in cases:
        source_pdf = resolve_file_uri(case["metadata"]["source_document"])
        document_pdf = resolve_file_uri(case["vars"]["document"])
        image_path = resolve_file_uri(case["vars"]["document_image"])

        if case["metadata"]["variant"] == "scanned":
            temporary_pdf = document_pdf.with_suffix(".ghostscript.pdf")
            run(
                "gs",
                "-q",
                "-dSAFER",
                "-dBATCH",
                "-dNOPAUSE",
                "-sDEVICE=pdfimage24",
                "-r140",
                f"-sOutputFile={temporary_pdf}",
                str(source_pdf),
            )
            canonicalize_pdf(temporary_pdf, document_pdf)
            temporary_pdf.unlink()
        else:
            document_pdf = resolve_file_uri(case["vars"]["document"])

        run(
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "1",
            "-r",
            "140",
            "-png",
            "-singlefile",
            str(document_pdf),
            str(image_path.with_suffix("")),
        )

    print(f"Rendered {len(cases)} sentinel page images in {IMAGE_DIR}")


if __name__ == "__main__":
    main()
