"""Render a side-by-side worksheet for human review of Illinois form codes."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_MANIFEST = Path(__file__).with_name("illinois_form_code_verification.json")
DEFAULT_OUTPUT = Path(__file__).with_name("illinois-form-code-review")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_first_page(pdf_path: Path, output_path: Path) -> None:
    output_prefix = output_path.with_suffix("")
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "1",
            "-r",
            "180",
            "-png",
            "-singlefile",
            str(pdf_path),
            str(output_prefix),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def _review_card(sample: dict, image_name: str, status: dict) -> str:
    values = {
        "sample_id": sample["sample_id"],
        "form_name": sample["form_name"],
        "printed_identifier": sample["printed_identifier"],
        "revision": sample["revision"],
        "canonical_form_id": sample["canonical_form_id"],
        "registry_form_id": sample["registry_form_id"],
        "code_family": sample["code_family"],
        "source_url": sample["source_url"],
        "landing_page_url": sample["landing_page_url"],
        "status": status.get("status", "pending"),
        "notes": status.get("notes", ""),
    }
    return f"""
    <section class="review-card">
      <div class="form-page">
        <img src="{html.escape(image_name)}" alt="First page of {html.escape(values['sample_id'])} {html.escape(values['form_name'])}">
      </div>
      <div class="assignment">
        <h2>{html.escape(values['sample_id'])}: {html.escape(values['form_name'])}</h2>
        <p class="instruction">Look at the rendered page and compare its printed code with the assigned value. This worksheet is for visual review; the extracted text is only supporting evidence.</p>
        <dl>
          <dt>Assigned printed code</dt><dd class="assigned-code">{html.escape(values['printed_identifier'])}</dd>
          <dt>Assigned revision</dt><dd>{html.escape(values['revision'])}</dd>
          <dt>Code family</dt><dd>{html.escape(values['code_family'])}</dd>
          <dt>Canonical form</dt><dd><code>{html.escape(values['canonical_form_id'])}</code></dd>
          <dt>Registry form ID</dt><dd><code>{html.escape(values['registry_form_id'])}</code></dd>
          <dt>Review status</dt><dd class="status">{html.escape(values['status'])}</dd>
          <dt>Review notes</dt><dd>{html.escape(values['notes']) or '—'}</dd>
        </dl>
        <p><a href="{html.escape(values['source_url'])}">Direct PDF source</a> · <a href="{html.escape(values['landing_page_url'])}">Illinois form page</a></p>
      </div>
    </section>
    """


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    manifest_path = (
        args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    )
    output_dir = args.output if args.output.is_absolute() else repo_root / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("pdftoppm") is None:
        parser.error("pdftoppm is required to render the PDF pages")

    manifest = _load_json(manifest_path)
    status_path = output_dir / "review_status.json"
    existing_status = _load_json(status_path) if status_path.exists() else {}
    existing_samples = {
        sample["sample_id"]: sample
        for sample in existing_status.get("samples", [])
        if isinstance(sample, dict) and sample.get("sample_id")
    }
    status_samples = []
    cards = []
    for sample in manifest["samples"]:
        sample_id = sample["sample_id"]
        image_name = f"{sample_id}-page-1.png"
        _render_first_page(
            repo_root
            / "benchmarking/synthetic/official_templates"
            / f"{sample_id}.pdf",
            output_dir / image_name,
        )
        status = existing_samples.get(sample_id, {"status": "pending", "notes": ""})
        status_samples.append(
            {
                "sample_id": sample_id,
                "status": status.get("status", "pending"),
                "reviewer": status.get("reviewer"),
                "reviewed_at": status.get("reviewed_at"),
                "notes": status.get("notes", ""),
            }
        )
        cards.append(_review_card(sample, image_name, status))

    status_path.write_text(
        json.dumps(
            {
                "generated_at": date.today().isoformat(),
                "instructions": "Statuses record visual confirmation of each rendered page. For a future correction, set the affected sample to needs_correction, add notes, and rerun this command.",
                "samples": status_samples,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Illinois form code review</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
    body {{ margin: 2rem auto; max-width: 1800px; padding: 0 1rem; color: #17202a; background: #f4f6f7; }}
    h1 {{ margin-bottom: .25rem; }}
    .intro {{ max-width: 75rem; }}
    .review-card {{ display: grid; grid-template-columns: minmax(38rem, 1fr) minmax(20rem, 27rem); gap: 1.5rem; align-items: start; margin: 2rem 0; padding: 1rem; background: white; border: 1px solid #ccd1d1; border-radius: .5rem; }}
    .form-page {{ overflow: auto; background: #687078; padding: .75rem; }}
    .form-page img {{ display: block; width: 100%; height: auto; background: white; }}
    .assignment {{ position: sticky; top: 1rem; }}
    .assigned-code {{ font-size: 1.4rem; font-weight: 700; color: #8e2c2c; }}
    .status {{ font-weight: 700; }}
    .instruction {{ background: #fff4ce; padding: .75rem; border-left: .3rem solid #d39e00; }}
    dt {{ margin-top: .8rem; font-weight: 700; }}
    dd {{ margin-left: 0; }}
    code {{ overflow-wrap: anywhere; }}
    @media (max-width: 900px) {{ .review-card {{ grid-template-columns: 1fr; }} .assignment {{ position: static; }} }}
  </style>
</head>
<body>
  <h1>Illinois form code review</h1>
  <p class="intro">Visually compare each assigned identifier and revision with the actual first page of the sampled official form. The automated scan is not a substitute for this review. Statuses are stored in <code>review_status.json</code>; edit that file and rerun the renderer to record a review.</p>
  {''.join(cards)}
</body>
</html>
"""
    (output_dir / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote visual review worksheet to {output_dir / 'index.html'}")
    print(f"Wrote review statuses to {status_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
