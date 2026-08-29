"""Management command: load the crosswalk JSON into CrosswalkForm / CrosswalkMapping."""

import json
import math
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from crosswalk_review.models import CrosswalkForm, CrosswalkMapping


def _text_value(data, key, *, model, context):
    """Read a nullable JSON value as text and enforce the model field limit."""
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CommandError(f"{context}.{key} must be a string or null.")
    max_length = model._meta.get_field(key).max_length
    if max_length is not None and len(value) > max_length:
        raise CommandError(f"{context}.{key} exceeds the {max_length}-character limit.")
    return value


def _boolean_value(data, key, *, default, context):
    """Read a nullable JSON value as a strict boolean."""
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise CommandError(f"{context}.{key} must be true, false, or null.")
    return value


def _string_list(value, *, context):
    """Validate a JSON list whose members must all be strings."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CommandError(f"{context} must be a list of strings or null.")
    return value


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
            # The same reviewed data is bundled with the Dockerized efile app,
            # or located in benchmarking/promptfoo/data/.
            base_dir = Path(settings.BASE_DIR)
            candidate_paths = [
                Path(settings.FORM_CODE_CROSSWALK_PATH),
                base_dir / "efile" / "data" / "form_code_crosswalk.json",
                base_dir.parent / "benchmarking" / "promptfoo" / "data" / "form_code_crosswalk.json",
                base_dir / "benchmarking" / "promptfoo" / "data" / "form_code_crosswalk.json",
            ]
            for candidate in candidate_paths:
                if candidate.exists():
                    json_path = candidate
                    break
            else:
                json_path = candidate_paths[0]

        json_path = Path(json_path)
        if not json_path.exists():
            raise CommandError(f"Crosswalk file not found: {json_path}")

        self.stdout.write(f"Loading crosswalk from {json_path} …")

        try:
            with json_path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read crosswalk JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise CommandError("Crosswalk JSON must contain an object at the top level.")
        registry = data.get("registry")
        if not isinstance(registry, list) or not registry:
            raise CommandError("Crosswalk JSON must contain a non-empty 'registry' list.")

        self.stdout.write(f"Found {len(registry)} entries in registry.")

        forms_created = 0
        forms_updated = 0
        mappings_created = 0
        mappings_updated = 0
        mappings_deleted = 0
        forms_deleted = 0
        seen_canonical_ids = set()

        with transaction.atomic():
            if options["clear"]:
                self.stdout.write(self.style.WARNING("Clearing existing crosswalk data …"))
                CrosswalkForm.objects.all().delete()

            for idx, entry in enumerate(registry):
                context = f"registry[{idx}]"
                if not isinstance(entry, dict):
                    raise CommandError(f"{context} must be an object.")
                form_data = entry.get("form")
                mappings_data = entry.get("mappings")
                if not isinstance(form_data, dict):
                    raise CommandError(f"{context}.form must be an object.")
                if not isinstance(mappings_data, list):
                    raise CommandError(f"{context}.mappings must be a list.")

                canonical_id = _text_value(
                    form_data,
                    "canonical_id",
                    model=CrosswalkForm,
                    context=f"{context}.form",
                ).strip()
                if not canonical_id:
                    raise CommandError(f"{context}.form.canonical_id is required.")
                if canonical_id in seen_canonical_ids:
                    raise CommandError(f"Duplicate canonical ID in crosswalk JSON: {canonical_id}")
                seen_canonical_ids.add(canonical_id)

                source_urls = _string_list(
                    form_data.get("source_urls"),
                    context=f"{context}.form.source_urls",
                )

                incoming_title = _text_value(
                    form_data, "canonical_name", model=CrosswalkForm, context=f"{context}.form"
                )
                incoming_form_id = _text_value(form_data, "form_id", model=CrosswalkForm, context=f"{context}.form")
                existing_form = CrosswalkForm.objects.filter(canonical_id=canonical_id).first()
                if (
                    existing_form
                    and existing_form.reviews.exists()
                    and (existing_form.canonical_name != incoming_title or existing_form.form_id != incoming_form_id)
                ):
                    raise CommandError(
                        f"{context}.form title or form ID changed after reviews were recorded. "
                        "Re-run with --clear to explicitly discard existing reviews."
                    )

                form_obj, created = CrosswalkForm.objects.update_or_create(
                    canonical_id=canonical_id,
                    defaults={
                        "jurisdiction": _text_value(
                            form_data, "jurisdiction", model=CrosswalkForm, context=f"{context}.form"
                        ),
                        "form_id": incoming_form_id,
                        "canonical_name": incoming_title,
                        "department": _text_value(
                            form_data, "department", model=CrosswalkForm, context=f"{context}.form"
                        ),
                        "description": _text_value(
                            form_data, "description", model=CrosswalkForm, context=f"{context}.form"
                        ),
                        "is_efileable": _boolean_value(
                            form_data, "is_efileable", default=False, context=f"{context}.form"
                        ),
                        "is_form": _boolean_value(form_data, "is_form", default=True, context=f"{context}.form"),
                        "source_urls": source_urls,
                        "raw_data": form_data,
                        "registry_index": idx,
                    },
                )
                if created:
                    forms_created += 1
                else:
                    forms_updated += 1

                for m_idx, m_data in enumerate(mappings_data):
                    mapping_context = f"{context}.mappings[{m_idx}]"
                    if not isinstance(m_data, dict):
                        raise CommandError(f"{mapping_context} must be an object.")
                    court_scope = m_data.get("court_scope") or {}
                    if not isinstance(court_scope, dict):
                        raise CommandError(f"{mapping_context}.court_scope must be an object or null.")
                    court_names = _string_list(
                        court_scope.get("court_names"),
                        context=f"{mapping_context}.court_scope.court_names",
                    )
                    confidence = m_data.get("confidence")
                    if confidence is not None:
                        if isinstance(confidence, bool) or not isinstance(confidence, int | float):
                            raise CommandError(f"{mapping_context}.confidence must be a number or null.")
                        confidence = float(confidence)
                        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                            raise CommandError(f"{mapping_context}.confidence must be between 0 and 1.")

                    mapping_defaults = {
                        "category": _text_value(m_data, "category", model=CrosswalkMapping, context=mapping_context),
                        "case_type": _text_value(m_data, "case_type", model=CrosswalkMapping, context=mapping_context),
                        "filing_type": _text_value(
                            m_data, "filing_type", model=CrosswalkMapping, context=mapping_context
                        ),
                        "filing_phase": _text_value(
                            m_data, "filing_phase", model=CrosswalkMapping, context=mapping_context
                        ),
                        "court_names": court_names,
                        "confidence": confidence,
                        "association_status": _text_value(
                            m_data, "association_status", model=CrosswalkMapping, context=mapping_context
                        ),
                        "catalog_status": _text_value(
                            m_data, "catalog_status", model=CrosswalkMapping, context=mapping_context
                        ),
                        "notes": _text_value(m_data, "notes", model=CrosswalkMapping, context=mapping_context),
                        "raw_data": m_data,
                    }
                    existing_mapping = CrosswalkMapping.objects.filter(
                        form=form_obj,
                        mapping_index=m_idx,
                    ).first()
                    review_target_fields = (
                        "category",
                        "case_type",
                        "filing_type",
                        "filing_phase",
                        "court_names",
                    )
                    target_changed = existing_mapping and any(
                        getattr(existing_mapping, field) != mapping_defaults[field] for field in review_target_fields
                    )
                    if target_changed and existing_mapping.verdicts.exists():
                        raise CommandError(
                            f"{mapping_context} changed after verdicts were recorded. "
                            "Re-run with --clear to explicitly discard existing reviews."
                        )

                    _, m_created = CrosswalkMapping.objects.update_or_create(
                        form=form_obj,
                        mapping_index=m_idx,
                        defaults=mapping_defaults,
                    )
                    if m_created:
                        mappings_created += 1
                    else:
                        mappings_updated += 1

                stale_mappings = form_obj.mappings.filter(mapping_index__gte=len(mappings_data))
                if stale_mappings.filter(verdicts__isnull=False).exists():
                    raise CommandError(
                        f"{context}.mappings removed mappings that have verdicts. "
                        "Re-run with --clear to explicitly discard existing reviews."
                    )
                stale_mapping_count = stale_mappings.count()
                if stale_mapping_count:
                    stale_mappings.delete()
                    mappings_deleted += stale_mapping_count

            stale_forms = CrosswalkForm.objects.exclude(canonical_id__in=seen_canonical_ids)
            if stale_forms.filter(Q(reviews__isnull=False) | Q(mappings__verdicts__isnull=False)).exists():
                raise CommandError(
                    "Crosswalk removal would delete forms with saved reviews. "
                    "Re-run with --clear to explicitly discard those reviews."
                )
            forms_deleted = stale_forms.count()
            if forms_deleted:
                stale_forms.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone!\n"
                f"  Forms:    {forms_created} created, {forms_updated} updated, {forms_deleted} deleted\n"
                f"  Mappings: {mappings_created} created, {mappings_updated} updated, "
                f"{mappings_deleted} deleted\n"
                f"  Total forms in DB: {CrosswalkForm.objects.count()}\n"
                f"  Total mappings in DB: {CrosswalkMapping.objects.count()}\n"
            )
        )
