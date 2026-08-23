"""Management command: load the crosswalk JSON into CrosswalkForm / CrosswalkMapping."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from crosswalk_review.models import CrosswalkForm, CrosswalkMapping


class Command(BaseCommand):
    help = "Load (or refresh) crosswalk data from form_code_crosswalk.json into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default=None,
            help="Override path to form_code_crosswalk.json",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing CrosswalkForm/CrosswalkMapping rows before loading.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        json_path = options["path"]
        if not json_path:
            # The same reviewed data is bundled with the Dockerized efile app.
            base_dir = Path(settings.BASE_DIR)
            json_path = base_dir / "efile" / "data" / "form_code_crosswalk.json"

        json_path = Path(json_path)
        if not json_path.exists():
            raise CommandError(f"Crosswalk file not found: {json_path}")

        self.stdout.write(f"Loading crosswalk from {json_path} …")

        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)

        registry = data.get("registry", [])
        if not registry:
            raise CommandError("No 'registry' key found in crosswalk JSON.")

        self.stdout.write(f"Found {len(registry)} entries in registry.")

        if options["clear"]:
            self.stdout.write(self.style.WARNING("Clearing existing crosswalk data …"))
            CrosswalkMapping.objects.all().delete()
            CrosswalkForm.objects.all().delete()

        forms_created = 0
        forms_updated = 0
        mappings_created = 0
        mappings_updated = 0

        with transaction.atomic():
            for idx, entry in enumerate(registry):
                form_data = entry.get("form", {})
                mappings_data = entry.get("mappings", [])

                canonical_id = form_data.get("canonical_id", "")
                if not canonical_id:
                    self.stderr.write(f"  Skipping entry {idx}: no canonical_id.")
                    continue

                form_obj, created = CrosswalkForm.objects.update_or_create(
                    canonical_id=canonical_id,
                    defaults={
                        "jurisdiction": form_data.get("jurisdiction", ""),
                        "form_id": form_data.get("form_id", ""),
                        "canonical_name": form_data.get("canonical_name", ""),
                        "department": form_data.get("department", ""),
                        "description": form_data.get("description", ""),
                        "is_efileable": bool(form_data.get("is_efileable", False)),
                        "is_form": bool(form_data.get("is_form", True)),
                        "source_urls": form_data.get("source_urls", []),
                        "raw_data": form_data,
                        "registry_index": idx,
                    },
                )
                if created:
                    forms_created += 1
                else:
                    forms_updated += 1

                for m_idx, m_data in enumerate(mappings_data):
                    court_scope = m_data.get("court_scope", {})
                    court_names = court_scope.get("court_names", [])
                    confidence = m_data.get("confidence")

                    mapping_obj, m_created = CrosswalkMapping.objects.update_or_create(
                        form=form_obj,
                        mapping_index=m_idx,
                        defaults={
                            "category": m_data.get("category", ""),
                            "case_type": m_data.get("case_type", ""),
                            "filing_type": m_data.get("filing_type", ""),
                            "filing_phase": m_data.get("filing_phase", ""),
                            "court_names": court_names,
                            "confidence": float(confidence) if confidence is not None else None,
                            "association_status": m_data.get("association_status", ""),
                            "catalog_status": m_data.get("catalog_status", ""),
                            "notes": m_data.get("notes", ""),
                            "raw_data": m_data,
                        },
                    )
                    if m_created:
                        mappings_created += 1
                    else:
                        mappings_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone!\n"
                f"  Forms:    {forms_created} created, {forms_updated} updated\n"
                f"  Mappings: {mappings_created} created, {mappings_updated} updated\n"
                f"  Total forms in DB: {CrosswalkForm.objects.count()}\n"
                f"  Total mappings in DB: {CrosswalkMapping.objects.count()}\n"
            )
        )
