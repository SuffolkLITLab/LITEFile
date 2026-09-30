"""Compare raw Gotenberg, LITEFile and PDFtk using local filled PDF forms.

From efile_app: uv run python ../testing/validate_document_preparation.py --output /tmp/pdf-validation
Rendered documents remain local. Publish only synthetic examples.
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "efile_app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "efile.settings_dev")
import django  # noqa: E402

django.setup()
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from efile.services.document_preparation import _gotenberg, prepare_document  # noqa: E402


def summary(content):
    reader = PdfReader(io.BytesIO(content))
    return {
        "pages": len(reader.pages),
        "remaining_fields": len(reader.get_fields() or {}),
        "text_characters": sum(len(page.extract_text() or "") for page in reader.pages),
        "tagged": bool(reader.trailer["/Root"].get("/StructTreeRoot")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        help="PDF or repository directory; defaults to ~/docassemble-*.",
    )
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    seen, report = set(), []
    for root in args.source or sorted(Path.home().glob("docassemble-*")):
        for path in [root] if root.is_file() else sorted(root.rglob("*.pdf")):
            if ".git" in path.parts:
                continue
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest in seen:
                continue
            try:
                reader = PdfReader(io.BytesIO(content))
                fields = reader.get_fields() or {}
                filled = [field for field in fields.values() if field.get("/V")]
                if not filled:
                    continue
            except Exception:
                continue
            seen.add(digest)
            folder = args.output / f"{len(report):02}"
            folder.mkdir(exist_ok=True)
            row = {
                "source": str(path.relative_to(root.parent)),
                "sha256": digest,
                "input_pages": len(reader.pages),
                "input_fields": len(fields),
                "filled_fields": len(filled),
                "multiline_fields": sum(
                    bool(int(field.get("/Ff", 0)) & 4096) for field in fields.values()
                ),
            }
            for engine in ["raw-gotenberg", "litefile", "pdftk"]:
                try:
                    target = folder / f"{engine}.pdf"
                    if engine == "raw-gotenberg":
                        output = _gotenberg(
                            content, ".pdf", "/forms/pdfengines/flatten"
                        )
                    elif engine == "litefile":
                        output = prepare_document(
                            SimpleUploadedFile("input.pdf", content), "vermont"
                        ).content
                    else:
                        subprocess.run(
                            ["pdftk", str(path), "output", str(target), "flatten"],
                            capture_output=True,
                            check=True,
                            timeout=45,
                        )
                        output = target.read_bytes()
                    target.write_bytes(output)
                    row[engine] = {"accepted": True, **summary(output)}
                    if args.render:
                        subprocess.run(
                            [
                                "pdftoppm",
                                "-f",
                                "1",
                                "-singlefile",
                                "-scale-to",
                                "1400",
                                "-png",
                                str(target),
                                str(folder / engine),
                            ],
                            capture_output=True,
                            check=True,
                            timeout=45,
                        )
                except Exception as error:
                    row[engine] = {
                        "accepted": False,
                        "error_type": type(error).__name__,
                    }
            report.append(row)
            print(
                row["source"],
                {
                    engine: row[engine]["accepted"]
                    for engine in ["raw-gotenberg", "litefile", "pdftk"]
                },
                flush=True,
            )
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Compared {len(report)} distinct filled PDFs.")


if __name__ == "__main__":
    main()
