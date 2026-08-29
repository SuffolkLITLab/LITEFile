"""Build the exact printed-ID reverse index for downloaded court PDFs."""

import json
from collections import defaultdict
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from markitdown import MarkItDown
from pypdf import PdfReader

from crosswalk_review.local_forms import _jurisdiction_key, _registry_rows, _text_key
from crosswalk_review.models import CrosswalkForm
from efile.services.taxonomy_classification import (
    _build_form_identifier_index,
    scan_text_for_form_identifier_index,
)

JURISDICTION_NAMES = {"il": "illinois", "ma": "massachusetts", "vt": "vermont"}


class Command(BaseCommand):
    """Create a fast canonical-form-to-local-PDF index from printed IDs."""

    help = "Scan local PDFs once and index unique exact printed form-ID matches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--forms-root",
            default="",
            help="Downloaded forms directory (defaults to the review setting).",
        )
        parser.add_argument(
            "--output",
            default="",
            help="Output path (defaults to <forms-root>/form_id_matches.json).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        configured_root = options["forms_root"] or getattr(settings, "CROSSWALK_REVIEW_FORMS_ROOT", "")
        forms_root = Path(configured_root or settings.BASE_DIR.parent / "court_forms").resolve()
        if not forms_root.is_dir():
            raise CommandError(f"Forms root does not exist: {forms_root}")

        forms = list(CrosswalkForm.objects.order_by("canonical_id"))
        registry = [
            {
                "form": {
                    "canonical_id": form.canonical_id,
                    "jurisdiction": form.jurisdiction,
                    "form_id": form.form_id,
                    "canonical_name": form.canonical_name,
                    # The review index intentionally includes paper-only forms.
                    "is_form": True,
                    "is_efileable": True,
                }
            }
            for form in forms
            if form.form_id.strip()
        ]
        identifier_index = _build_form_identifier_index(registry)
        canonical_ids_by_identifier: dict[tuple[str, str], set[str]] = defaultdict(set)
        for form in forms:
            identifier = _text_key(form.form_id)
            if identifier:
                canonical_ids_by_identifier[(form.jurisdiction.casefold(), identifier)].add(form.canonical_id)
        matches_by_form: dict[str, set[str]] = defaultdict(set)
        unreadable_paths = []
        scanned_pdfs = 0
        pypdf_matches = 0
        markitdown_matches = 0
        markitdown = MarkItDown()

        def canonical_matches(jurisdiction, text):
            result = scan_text_for_form_identifier_index(identifier_index, jurisdiction, text)
            matches = set()
            for match in result["matches"]:
                canonical_id = str(match["canonical_form_id"])
                if any(
                    canonical_ids_by_identifier[(jurisdiction.casefold(), identifier)] == {canonical_id}
                    for identifier in match["normalized_identifiers"]
                ):
                    matches.add(canonical_id)
            return matches

        registry_rows = _registry_rows(forms_root)
        title_by_path = {
            str(row.get("relative_path") or row.get("filename") or "").strip(): _text_key(
                str(row.get("canonical_title") or row.get("title") or "")
            )
            for row in registry_rows
        }
        for row_number, row in enumerate(registry_rows, start=1):
            relative_path = str(row.get("relative_path") or row.get("filename") or "").strip()
            path = (forms_root / relative_path).resolve()
            if not relative_path or path.suffix.casefold() != ".pdf" or not path.is_file():
                continue
            jurisdiction_key = _jurisdiction_key(str(row.get("jurisdiction") or relative_path.split("/", 1)[0]))
            jurisdiction = JURISDICTION_NAMES.get(jurisdiction_key, jurisdiction_key)
            try:
                text = "\f".join(page.extract_text() or "" for page in PdfReader(path).pages)
                canonical_ids = canonical_matches(jurisdiction, text)
            except Exception as error:  # MarkItDown may still recover the text.
                text = ""
                canonical_ids = set()
                pypdf_error = str(error)
            else:
                pypdf_error = ""
            scanned_pdfs += 1
            source = "pypdf" if canonical_ids else ""
            if pypdf_error or not text.strip():
                try:
                    text = markitdown.convert(path).text_content
                    canonical_ids = canonical_matches(jurisdiction, text)
                    source = "markitdown" if canonical_ids else ""
                    markitdown_error = ""
                except Exception as error:
                    markitdown_error = str(error)
            else:
                markitdown_error = ""
            if not canonical_ids and pypdf_error and markitdown_error:
                unreadable_paths.append(
                    {"path": relative_path, "pypdf_error": pypdf_error, "markitdown_error": markitdown_error}
                )
            if source == "pypdf":
                pypdf_matches += 1
            elif source == "markitdown":
                markitdown_matches += 1
            for canonical_id in canonical_ids:
                matches_by_form[canonical_id].add(relative_path)
            if row_number % 250 == 0:
                self.stdout.write(f"Scanned {row_number} registry entries…")

        results = {}
        for form in forms:
            candidate_paths = sorted(matches_by_form.get(form.canonical_id, ()))
            raw_data = form.raw_data if isinstance(form.raw_data, dict) else {}
            aliases = raw_data.get("aliases", []) if isinstance(raw_data.get("aliases", []), list) else []
            form_titles = {_text_key(form.canonical_name), *(_text_key(alias) for alias in aliases)} - {""}

            def title_corresponds(path, titles=form_titles):
                candidate_title = title_by_path.get(path, "")
                if not candidate_title:
                    return False
                return any(
                    title in candidate_title
                    or candidate_title in title
                    or SequenceMatcher(None, title, candidate_title).ratio() >= 0.78
                    for title in titles
                )

            title_matched_paths = [path for path in candidate_paths if title_corresponds(path)]
            if len(candidate_paths) == 1:
                status = "unique_printed_id_match"
            elif len(title_matched_paths) == 1:
                candidate_paths = title_matched_paths
                status = "unique_printed_id_and_title_match"
            elif title_matched_paths:
                candidate_paths = title_matched_paths
                status = "printed_id_form_family"
            elif candidate_paths:
                status = "multiple_printed_id_matches"
            elif not form.form_id.strip():
                status = "no_assigned_id"
            else:
                status = "no_printed_id_match"
            results[form.canonical_id] = {
                "status": status,
                "candidate_paths": candidate_paths,
            }

        summary = {
            "generated_at": datetime.now(UTC).isoformat(),
            "forms_root": str(forms_root),
            "scanned_pdfs": scanned_pdfs,
            "unreadable_pdfs": len(unreadable_paths),
            "forms": len(forms),
            "unique_printed_id_matches": sum(
                result["status"] == "unique_printed_id_match" for result in results.values()
            ),
            "multiple_printed_id_matches": sum(
                result["status"] == "multiple_printed_id_matches" for result in results.values()
            ),
            "unique_printed_id_and_title_matches": sum(
                result["status"] == "unique_printed_id_and_title_match" for result in results.values()
            ),
            "printed_id_form_families": sum(
                result["status"] == "printed_id_form_family" for result in results.values()
            ),
            "pypdf_matched_pdfs": pypdf_matches,
            "markitdown_matched_pdfs": markitdown_matches,
        }
        output_path = Path(options["output"]).expanduser() if options["output"] else forms_root / "form_id_matches.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {"summary": summary, "forms": results, "unreadable_pdfs": unreadable_paths},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
        self.stdout.write(f"Wrote {output_path}")
