"""Audit whether crosswalk form IDs are printed in locally downloaded PDFs."""

import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from crosswalk_review.local_forms import resolve_local_form, verify_local_form_id
from crosswalk_review.models import CrosswalkForm


class Command(BaseCommand):
    """Report local-PDF identity evidence for every loaded crosswalk form."""

    help = "Check that each assigned form ID appears in its resolved local PDF."

    def add_arguments(self, parser):
        parser.add_argument(
            "--forms-root",
            default="",
            help="Downloaded forms directory (defaults to the review setting).",
        )
        parser.add_argument(
            "--output",
            default="",
            help="Optional path for a JSON report with every form result.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        configured_root = options["forms_root"] or getattr(settings, "CROSSWALK_REVIEW_FORMS_ROOT", "")
        forms_root = Path(configured_root or settings.BASE_DIR.parent / "court_forms").resolve()
        if not forms_root.is_dir():
            raise CommandError(f"Forms root does not exist: {forms_root}")

        rows = []
        counts = Counter()
        forms = CrosswalkForm.objects.order_by("canonical_id").iterator()
        for form in forms:
            document, method = resolve_local_form(form, forms_root)
            if not document:
                status = "no_local_candidate"
                verification = None
            else:
                verification = verify_local_form_id(form, document)
                status = verification.status
            counts[status] += 1
            rows.append(
                {
                    "canonical_id": form.canonical_id,
                    "jurisdiction": form.jurisdiction,
                    "assigned_form_id": form.form_id,
                    "canonical_name": form.canonical_name,
                    "status": status,
                    "candidate_path": document.relative_path if document else "",
                    "candidate_match_method": method,
                    "matched_page": verification.page if verification else None,
                    "error": verification.error if verification else "",
                }
            )

        summary = {
            "forms_root": str(forms_root),
            "total_forms": len(rows),
            "counts": dict(sorted(counts.items())),
            "verified_forms": counts["verified"],
            "unverified_forms": len(rows) - counts["verified"],
        }
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
        if options["output"]:
            output_path = Path(options["output"]).expanduser()
            if output_path.exists() and output_path.is_dir():
                raise CommandError(f"Output path is a directory: {output_path}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps({"summary": summary, "forms": rows}, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.stdout.write(f"Wrote {output_path}")
