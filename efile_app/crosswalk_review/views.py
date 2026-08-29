"""Views for the crosswalk_review app."""

import csv
import json
import os
import re
from datetime import UTC, datetime
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods
from requests import RequestException

from efile.services.taxonomy_classification import TylerTaxonomyClient

from .local_forms import resolve_local_form, verify_local_form_id
from .models import CrosswalkForm, CrosswalkMapping, FormReview, MappingVerdict

LITEFILE_BASE_URL = os.environ.get("LITEFILE_BASE_URL", "https://litefile-staging.fly.dev")
REVIEW_EFSP_URL = getattr(
    settings,
    "CROSSWALK_REVIEW_EFSP_URL",
    os.environ.get("CROSSWALK_REVIEW_EFSP_URL", getattr(settings, "EFSP_URL", "")),
).rstrip("/")
MAX_REVIEWER_NAME_LENGTH = MappingVerdict._meta.get_field("reviewer_name").max_length
VERDICTS = {choice[0] for choice in MappingVerdict.VERDICT_CHOICES}
REVIEW_LEVELS = ("category", "case_type", "filing_type")
LOOKUP_FILING_PHASES = {"initial", "subsequent"}
JURISDICTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,99}$")
# Current Tyler court keys include values such as ``appeals:acp``,
# ``sc:chittendon``, and the legacy Illinois key ``reaknox 2``. Slashes,
# percent escapes, query delimiters, and traversal characters remain blocked.
ROUTE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _:-]{0,99}$")


def _local_forms_root():
    """Return the local downloaded-forms directory used by the review tool."""
    configured_root = getattr(settings, "CROSSWALK_REVIEW_FORMS_ROOT", "")
    if configured_root:
        return configured_root
    return settings.BASE_DIR.parent / "court_forms"


def _reviewer_from_request(request):
    """Extract reviewer name from POST, GET, or session."""
    candidates = (
        request.POST.get("reviewer_name", ""),
        request.GET.get("reviewer", ""),
        request.session.get("reviewer_name", ""),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and (reviewer := " ".join(candidate.split())):
            return reviewer
    return ""


def _reviewer_url(url_name, reviewer, *, args=None, extra=None):
    """Build an internal URL with a safely encoded reviewer query parameter."""
    params = {"reviewer": reviewer, **(extra or {})}
    return f"{reverse(url_name, args=args)}?{urlencode(params)}"


def _forms_with_review_counts(queryset=None, *, reviewer=None):
    """Annotate forms with mapping and reviewed-mapping counts."""
    queryset = queryset if queryset is not None else CrosswalkForm.objects.all()
    reviewed_filter = Q(mappings__verdicts__isnull=False)
    if reviewer is not None:
        reviewed_filter &= Q(mappings__verdicts__reviewer_name=reviewer)
    return queryset.annotate(
        mapping_count=Count("mappings", distinct=True),
        reviewed_mapping_count=Count("mappings", filter=reviewed_filter, distinct=True),
    )


def _reviewed_mapping_value(verdict, level, assigned_value):
    """Return a saved answer, falling back to the assigned crosswalk value."""
    value = getattr(verdict, f"reviewed_{level}", "") if verdict else ""
    return value or assigned_value or ""


def _field_verdict(verdict, level):
    """Return the saved field verdict, or the legacy overall verdict if present."""
    if not verdict:
        return ""
    field_verdicts = verdict.field_verdicts if isinstance(verdict.field_verdicts, dict) else {}
    value = field_verdicts.get(level, "")
    if value in VERDICTS:
        return value
    # Existing MappingVerdict rows predate field-level review. Treat their
    # overall answer as a display-only starting point; the reviewer can refine
    # each field before marking the form complete.
    return verdict.verdict if verdict.verdict in VERDICTS else ""


def _related_objects(obj, relation):
    """Use prefetched related objects when available, otherwise query normally."""
    cache = getattr(obj, "_prefetched_objects_cache", {})
    if relation in cache:
        return cache[relation]
    return list(getattr(obj, relation).all())


def _review_progress(form_obj, reviewer):
    """Return field-level progress for one reviewer and one form."""
    mappings = _related_objects(form_obj, "mappings")
    form_review = next(
        (review for review in _related_objects(form_obj, "reviews") if review.reviewer_name == reviewer),
        None,
    )
    mapping_reviews = {
        verdict.mapping_id: verdict
        for mapping in mappings
        for verdict in _related_objects(mapping, "verdicts")
        if verdict.reviewer_name == reviewer
    }
    identity_statuses = (
        form_review.title_verdict if form_review else "",
        form_review.form_id_verdict if form_review else "",
    )
    identity_reviewed = sum(status in VERDICTS for status in identity_statuses)
    mapping_total = len(mappings)
    mapping_reviewed = sum(
        sum(_field_verdict(mapping_reviews.get(mapping.pk), level) in VERDICTS for level in REVIEW_LEVELS)
        for mapping in mappings
    )
    total_fields = 2 + (mapping_total * len(REVIEW_LEVELS))
    reviewed_fields = identity_reviewed + mapping_reviewed
    return {
        "form_review": form_review,
        "mapping_reviews": mapping_reviews,
        "reviewed_fields": reviewed_fields,
        "total_fields": total_fields,
        "complete": reviewed_fields == total_fields,
    }


def _court_specs(mapping):
    """Return the mapped court names paired with their observed route keys."""
    raw_scope = mapping.raw_data.get("court_scope", {}) if isinstance(mapping.raw_data, dict) else {}
    names = mapping.court_names or []
    route_keys = raw_scope.get("observed_route_keys", []) if isinstance(raw_scope, dict) else []
    return [
        {"name": name, "route_key": route_keys[index] if index < len(route_keys) else ""}
        for index, name in enumerate(names)
    ]


def _taxonomy_client():
    """Build the live lookup client pointed at the configured staging API."""
    return TylerTaxonomyClient(base_url=REVIEW_EFSP_URL, timeout=10, attempts=3)


def _route_key(request, name):
    value = " ".join(request.GET.get(name, "").split())
    if not value or not ROUTE_KEY_RE.fullmatch(value):
        raise ValueError(f"A valid {name} route key is required.")
    return value


@require_GET
def taxonomy_options(request, level):
    """Return live staged taxonomy options for the review page's cascading selectors."""
    if level not in {"courts", "categories", "case_types", "filing_types"}:
        return JsonResponse({"error": "Unknown taxonomy level."}, status=404)

    jurisdiction = " ".join(request.GET.get("jurisdiction", "").split()).casefold()
    if not jurisdiction or not JURISDICTION_RE.fullmatch(jurisdiction):
        return JsonResponse({"error": "A valid jurisdiction is required."}, status=400)
    filing_phase = request.GET.get("filing_phase", "initial").strip().casefold()
    if filing_phase not in LOOKUP_FILING_PHASES:
        return JsonResponse({"error": "Filing phase must be initial or subsequent."}, status=400)

    try:
        if level == "courts":
            client = _taxonomy_client()
            options = client.courts(jurisdiction)
        elif level == "categories":
            court = _route_key(request, "court")
            client = _taxonomy_client()
            options = client.categories(jurisdiction, court, filing_phase)
        elif level == "case_types":
            court = _route_key(request, "court")
            category = _route_key(request, "category")
            client = _taxonomy_client()
            options = client.case_types(
                jurisdiction,
                court,
                category,
                filing_phase,
            )
        else:
            court = _route_key(request, "court")
            category = _route_key(request, "category")
            case_type = _route_key(request, "case_type")
            client = _taxonomy_client()
            options = client.filing_types(
                jurisdiction,
                court,
                category,
                case_type,
                filing_phase,
            )
    except (RequestException, ValueError) as error:
        return JsonResponse({"error": f"Live lookup failed: {error}"}, status=502)

    return JsonResponse(
        {
            "level": level,
            "endpoint": client.base_url,
            "checked_at": datetime.now(UTC).isoformat(),
            "options": options,
        }
    )


@require_GET
@xframe_options_sameorigin
def local_form_pdf(request, canonical_id):
    """Serve the matched working-directory PDF inline in the browser."""
    form_obj = get_object_or_404(CrosswalkForm, canonical_id=canonical_id)
    document, _ = resolve_local_form(form_obj, _local_forms_root())
    if not document:
        raise Http404("No local PDF is available for this form.")
    verification = verify_local_form_id(form_obj, document)
    if not verification.verified:
        raise Http404("The local PDF does not verify this form's assigned ID.")

    try:
        pdf_file = document.path.open("rb")
    except OSError as error:
        raise Http404("The local PDF is no longer available.") from error

    response = FileResponse(pdf_file, content_type="application/pdf")
    safe_filename = re.sub(r'["\\\r\n]', "_", document.filename)
    response["Content-Disposition"] = f'inline; filename="{safe_filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_http_methods(["GET", "POST"])
def index(request):
    """Landing page – reviewer enters name, sees progress stats."""
    reviewer = _reviewer_from_request(request)

    reviewer_error = ""
    if len(reviewer) > MAX_REVIEWER_NAME_LENGTH:
        reviewer_error = f"Your name must be {MAX_REVIEWER_NAME_LENGTH} characters or fewer."
    elif request.method == "POST" and not reviewer:
        reviewer_error = "Enter your name to start reviewing."
    elif request.method == "POST":
        request.session["reviewer_name"] = reviewer
        return redirect(
            _reviewer_url(
                "crosswalk_review:next_unreviewed",
                reviewer,
                extra={"workflow": "fields"},
            )
        )

    # Stats
    total_forms = CrosswalkForm.objects.count()
    total_mappings = CrosswalkMapping.objects.count()
    total_verdicts = MappingVerdict.objects.count()
    total_form_reviews = FormReview.objects.count()

    # Preserve the original mapping-verdict statistic for existing reviewers.
    # The field-level completion statistic below is the one used by the new
    # resumable workflow.
    forms_fully_reviewed = (
        _forms_with_review_counts()
        .filter(
            mapping_count__gt=0,
            reviewed_mapping_count=F("mapping_count"),
        )
        .count()
    )
    forms_for_progress = CrosswalkForm.objects.prefetch_related("mappings__verdicts", "reviews")
    forms_field_complete = (
        sum(_review_progress(form_obj, reviewer)["complete"] for form_obj in forms_for_progress) if reviewer else 0
    )
    overall_progress_percent = round(forms_fully_reviewed / total_forms * 100) if total_forms else 0
    field_progress_percent = round(forms_field_complete / total_forms * 100) if total_forms else 0

    reviewer_stats = []
    if reviewer and not reviewer_error:
        my_verdict_count = MappingVerdict.objects.filter(reviewer_name=reviewer).count()
        my_form_review_count = FormReview.objects.filter(reviewer_name=reviewer).count()
        # Count distinct forms this reviewer has submitted any saved answer for.
        my_forms_touched = (
            CrosswalkForm.objects.filter(
                Q(mappings__verdicts__reviewer_name=reviewer) | Q(reviews__reviewer_name=reviewer)
            )
            .distinct()
            .count()
        )
        reviewer_stats = {
            "name": reviewer,
            "verdicts": my_verdict_count,
            "form_reviews": my_form_review_count,
            "forms_touched": my_forms_touched,
        }

    context = {
        "reviewer": reviewer,
        "total_forms": total_forms,
        "total_mappings": total_mappings,
        "total_verdicts": total_verdicts,
        "total_form_reviews": total_form_reviews,
        "forms_fully_reviewed": forms_fully_reviewed,
        "forms_field_complete": forms_field_complete,
        "overall_progress_percent": overall_progress_percent,
        "field_progress_percent": field_progress_percent,
        "reviewer_stats": reviewer_stats,
        "reviewer_error": reviewer_error,
        "litefile_base_url": LITEFILE_BASE_URL,
        "review_efsp_url": REVIEW_EFSP_URL,
    }
    return render(request, "crosswalk_review/index.html", context)


@require_http_methods(["GET", "POST"])
def review_form(request, canonical_id):
    """Show one form and save identity and taxonomy field-level answers."""
    form_obj = get_object_or_404(
        CrosswalkForm.objects.prefetch_related("mappings__verdicts", "reviews"),
        canonical_id=canonical_id,
    )
    reviewer = _reviewer_from_request(request)

    if not reviewer or len(reviewer) > MAX_REVIEWER_NAME_LENGTH:
        target = reverse("crosswalk_review:index")
        if reviewer:
            target = f"{target}?{urlencode({'reviewer': reviewer})}"
        return redirect(target)

    # Persist reviewer name in session
    request.session["reviewer_name"] = reviewer

    mappings = sorted(_related_objects(form_obj, "mappings"), key=lambda mapping: mapping.mapping_index)
    form_review = next(
        (review for review in form_obj.reviews.all() if review.reviewer_name == reviewer),
        None,
    )
    existing_verdicts = {
        verdict.mapping_id: verdict
        for mapping in mappings
        for verdict in mapping.verdicts.all()
        if verdict.reviewer_name == reviewer
    }

    submission_error = ""
    saved_message = request.GET.get("saved") == "1"
    if request.method == "POST":
        action = request.POST.get("action", "save_next")
        is_legacy_submission = "action" not in request.POST
        submitted_title_verdict = request.POST.get("title_verdict", "").strip()
        submitted_form_id_verdict = request.POST.get("form_id_verdict", "").strip()
        submitted_field_verdicts = {
            mapping.pk: {
                level: request.POST.get(f"{level}_verdict_{mapping.pk}", "").strip() for level in REVIEW_LEVELS
            }
            for mapping in mappings
        }

        if action not in {"save", "save_next"}:
            submission_error = "Unknown save action."
        elif is_legacy_submission:
            invalid_mappings = [
                mapping for mapping in mappings if request.POST.get(f"verdict_{mapping.pk}", "").strip() not in VERDICTS
            ]
            if invalid_mappings:
                submission_error = "Choose a verdict for every mapping before continuing."
        elif not is_legacy_submission and action == "save_next":
            invalid_identity = [
                label
                for label, value in {
                    "form title": submitted_title_verdict,
                    "form ID": submitted_form_id_verdict,
                }.items()
                if value not in VERDICTS
            ]
            invalid_fields = [
                mapping
                for mapping in mappings
                if any(value not in VERDICTS for value in submitted_field_verdicts[mapping.pk].values())
            ]
            if invalid_identity or invalid_fields:
                missing = ", ".join(invalid_identity)
                if invalid_fields:
                    mapping_text = "mapping" if len(invalid_fields) == 1 else "mappings"
                    missing = f"{missing}; field answers are missing for {len(invalid_fields)} {mapping_text}".lstrip(
                        "; "
                    )
                submission_error = f"Choose Correct, Incorrect, or Unsure for {missing} before continuing."

        if not submission_error:
            with transaction.atomic():
                form_review, _ = FormReview.objects.update_or_create(
                    form=form_obj,
                    reviewer_name=reviewer,
                    defaults={
                        "reviewed_title": request.POST.get("reviewed_title", form_obj.canonical_name).strip(),
                        "title_verdict": submitted_title_verdict,
                        "reviewed_form_id": request.POST.get("reviewed_form_id", form_obj.form_id).strip(),
                        "form_id_verdict": submitted_form_id_verdict,
                        "reviewer_notes": request.POST.get("form_notes", "").strip(),
                    },
                )
                for mapping in mappings:
                    previous = existing_verdicts.get(mapping.pk)
                    field_verdicts = submitted_field_verdicts[mapping.pk]
                    if is_legacy_submission:
                        overall = request.POST.get(f"verdict_{mapping.pk}", "").strip()
                        if overall not in VERDICTS:
                            continue
                        reviewed_values = {
                            level: _reviewed_mapping_value(previous, level, getattr(mapping, level))
                            for level in REVIEW_LEVELS
                        }
                    else:
                        reviewed_values = {
                            level: request.POST.get(
                                f"{level}_{mapping.pk}",
                                _reviewed_mapping_value(previous, level, getattr(mapping, level)),
                            ).strip()
                            for level in REVIEW_LEVELS
                        }
                        overall_values = set(field_verdicts.values())
                        if overall_values == {"correct"}:
                            overall = "correct"
                        elif "incorrect" in overall_values:
                            overall = "incorrect"
                        elif "unsure" in overall_values:
                            overall = "unsure"
                        else:
                            overall = ""
                    lookup_context = {}
                    raw_lookup = request.POST.get(f"lookup_{mapping.pk}", "").strip()
                    if raw_lookup:
                        try:
                            decoded_lookup = json.loads(raw_lookup)
                        except json.JSONDecodeError:
                            decoded_lookup = {}
                        if isinstance(decoded_lookup, dict):
                            lookup_context = decoded_lookup
                    MappingVerdict.objects.update_or_create(
                        mapping=mapping,
                        reviewer_name=reviewer,
                        defaults={
                            "verdict": overall,
                            "reviewed_category": reviewed_values["category"],
                            "reviewed_case_type": reviewed_values["case_type"],
                            "reviewed_filing_type": reviewed_values["filing_type"],
                            "field_verdicts": field_verdicts,
                            "lookup_context": lookup_context,
                            "reviewer_notes": request.POST.get(f"notes_{mapping.pk}", "").strip(),
                        },
                    )
            if action == "save_next":
                return redirect(
                    _reviewer_url(
                        "crosswalk_review:next_unreviewed",
                        reviewer,
                        extra={"workflow": "fields"},
                    )
                )
            return redirect(
                f"{reverse('crosswalk_review:review_form', args=[canonical_id])}"
                f"?{urlencode({'reviewer': reviewer, 'saved': '1'})}"
            )

        # Redisplay submitted values after a validation error without losing
        # anything the reviewer typed.
        if request.method == "POST":
            form_review = FormReview(
                form=form_obj,
                reviewer_name=reviewer,
                reviewed_title=request.POST.get("reviewed_title", form_obj.canonical_name).strip(),
                title_verdict=submitted_title_verdict,
                reviewed_form_id=request.POST.get("reviewed_form_id", form_obj.form_id).strip(),
                form_id_verdict=submitted_form_id_verdict,
                reviewer_notes=request.POST.get("form_notes", "").strip(),
            )
            existing_verdicts = {
                mapping.pk: MappingVerdict(
                    mapping=mapping,
                    reviewer_name=reviewer,
                    verdict=request.POST.get(f"verdict_{mapping.pk}", "").strip(),
                    reviewed_category=request.POST.get(f"category_{mapping.pk}", "").strip(),
                    reviewed_case_type=request.POST.get(f"case_type_{mapping.pk}", "").strip(),
                    reviewed_filing_type=request.POST.get(f"filing_type_{mapping.pk}", "").strip(),
                    field_verdicts=submitted_field_verdicts[mapping.pk],
                    reviewer_notes=request.POST.get(f"notes_{mapping.pk}", "").strip(),
                )
                for mapping in mappings
            }

    mapping_rows = []
    for mapping in mappings:
        existing = existing_verdicts.get(mapping.pk)
        court_names = mapping.court_names or []
        saved_lookup = existing.lookup_context if existing and isinstance(existing.lookup_context, dict) else {}
        saved_phase = str(saved_lookup.get("filing_phase", "")).strip().casefold()
        assigned_phase = mapping.filing_phase.strip().casefold()
        if saved_phase in LOOKUP_FILING_PHASES:
            lookup_filing_phase = saved_phase
        elif assigned_phase in LOOKUP_FILING_PHASES:
            lookup_filing_phase = assigned_phase
        else:
            lookup_filing_phase = "initial"
        mapping_rows.append(
            {
                "obj": mapping,
                "court_names_display": ", ".join(court_names) if court_names else "—",
                "court_specs": _court_specs(mapping),
                "reviewed_category": _reviewed_mapping_value(existing, "category", mapping.category),
                "reviewed_case_type": _reviewed_mapping_value(existing, "case_type", mapping.case_type),
                "reviewed_filing_type": _reviewed_mapping_value(existing, "filing_type", mapping.filing_type),
                "selected_verdict": existing.verdict if existing else "",
                "category_verdict": _field_verdict(existing, "category"),
                "case_type_verdict": _field_verdict(existing, "case_type"),
                "filing_type_verdict": _field_verdict(existing, "filing_type"),
                "reviewer_notes": existing.reviewer_notes if existing else "",
                "lookup_context": saved_lookup,
                "lookup_filing_phase": lookup_filing_phase,
                "uses_lookup_phase_fallback": assigned_phase not in LOOKUP_FILING_PHASES,
            }
        )

    # Prev / Next navigation
    all_ids = list(
        CrosswalkForm.objects.values_list("canonical_id", flat=True).order_by("registry_index", "canonical_id")
    )
    try:
        current_idx = all_ids.index(canonical_id)
    except ValueError:
        current_idx = 0
    prev_id = all_ids[current_idx - 1] if current_idx > 0 else None
    next_id = all_ids[current_idx + 1] if current_idx < len(all_ids) - 1 else None

    context = {
        "form_obj": form_obj,
        "reviewer": reviewer,
        "mapping_rows": mapping_rows,
        "prev_id": prev_id,
        "next_id": next_id,
        "current_num": current_idx + 1,
        "total_forms": len(all_ids),
        "litefile_base_url": LITEFILE_BASE_URL,
        "has_verdicts": bool(existing_verdicts),
        "form_review": form_review,
        "reviewed_title": form_review.reviewed_title if form_review else form_obj.canonical_name,
        "title_verdict": form_review.title_verdict if form_review else "",
        "reviewed_form_id": form_review.reviewed_form_id if form_review else form_obj.form_id,
        "form_id_verdict": form_review.form_id_verdict if form_review else "",
        "form_notes": form_review.reviewer_notes if form_review else "",
        "saved_message": saved_message,
        "review_efsp_url": REVIEW_EFSP_URL,
        "local_pdf_url": None,
        "local_pdf_filename": "",
        "local_pdf_relative_path": "",
        "local_pdf_match_method": "",
        "local_pdf_verification": None,
        "submission_error": submission_error,
    }
    local_document, local_match_method = resolve_local_form(form_obj, _local_forms_root())
    if local_document:
        local_verification = verify_local_form_id(form_obj, local_document)
        context.update(
            {
                "local_pdf_url": (
                    reverse("crosswalk_review:local_form_pdf", args=[form_obj.canonical_id])
                    if local_verification.verified
                    else None
                ),
                "local_pdf_filename": local_document.filename,
                "local_pdf_relative_path": local_document.relative_path,
                "local_pdf_match_method": local_match_method,
                "local_pdf_verification": local_verification,
            }
        )
    return render(request, "crosswalk_review/review.html", context)


@require_GET
def next_unreviewed(request):
    """Redirect to the next form this reviewer has not completed."""
    reviewer = _reviewer_from_request(request)
    if not reviewer or len(reviewer) > MAX_REVIEWER_NAME_LENGTH:
        return redirect(reverse("crosswalk_review:index"))

    request.session["reviewer_name"] = reviewer
    field_workflow = request.GET.get("workflow") == "fields"
    if field_workflow:
        forms = CrosswalkForm.objects.prefetch_related("mappings__verdicts", "reviews").order_by(
            "registry_index", "canonical_id"
        )
        for form_obj in forms:
            if not _review_progress(form_obj, reviewer)["complete"]:
                return redirect(
                    _reviewer_url(
                        "crosswalk_review:review_form",
                        reviewer,
                        args=[form_obj.canonical_id],
                    )
                )
    else:
        # Keep the original mapping-only route available for old review links.
        unreviewed = (
            _forms_with_review_counts(reviewer=reviewer)
            .filter(mapping_count__gt=0, reviewed_mapping_count__lt=F("mapping_count"))
            .order_by("registry_index", "canonical_id")
            .first()
        )
        if unreviewed:
            return redirect(_reviewer_url("crosswalk_review:review_form", reviewer, args=[unreviewed.canonical_id]))
    if not CrosswalkForm.objects.exists():
        return redirect(reverse("crosswalk_review:index"))
    return redirect(_reviewer_url("crosswalk_review:progress", reviewer))


@require_GET
def progress(request):
    """Summary page showing review progress per form and per reviewer."""
    reviewer = _reviewer_from_request(request)

    # Per-form stats: mapping count and verdict count (any reviewer)
    forms = list(
        _forms_with_review_counts()
        .annotate(
            verdict_count=Count("mappings__verdicts", distinct=True),
        )
        .prefetch_related("mappings__verdicts", "reviews")
        .order_by("registry_index", "canonical_id")
    )
    if reviewer:
        for form_obj in forms:
            form_obj.field_review_progress = _review_progress(form_obj, reviewer)

    # Per-reviewer totals
    reviewer_totals = MappingVerdict.objects.values("reviewer_name").annotate(total=Count("id")).order_by("-total")

    context = {
        "forms": forms,
        "reviewer_totals": reviewer_totals,
        "reviewer": reviewer,
        "total_forms": CrosswalkForm.objects.count(),
        "total_verdicts": MappingVerdict.objects.count(),
        "total_form_reviews": FormReview.objects.count(),
        "review_efsp_url": REVIEW_EFSP_URL,
    }
    return render(request, "crosswalk_review/progress.html", context)


@require_GET
def export_csv(request):
    """Download all verdicts as a CSV file."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="crosswalk_verdicts.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "canonical_id",
            "canonical_name",
            "jurisdiction",
            "mapping_index",
            "category",
            "case_type",
            "filing_type",
            "filing_phase",
            "confidence",
            "catalog_status",
            "association_status",
            "reviewer_name",
            "verdict",
            "reviewer_notes",
            "created_at",
            "updated_at",
            "reviewed_title",
            "title_verdict",
            "reviewed_form_id",
            "form_id_verdict",
            "form_reviewer_notes",
            "reviewed_category",
            "reviewed_case_type",
            "reviewed_filing_type",
            "field_verdicts",
            "lookup_context",
        ]
    )

    form_reviews = {(review.form_id, review.reviewer_name): review for review in FormReview.objects.all()}

    verdicts = MappingVerdict.objects.select_related("mapping__form").order_by(
        "mapping__form__canonical_id", "mapping__mapping_index", "reviewer_name"
    )

    for v in verdicts:
        m = v.mapping
        f = m.form
        form_review = form_reviews.get((f.pk, v.reviewer_name))
        writer.writerow(
            [
                _csv_safe(f.canonical_id),
                _csv_safe(f.canonical_name),
                _csv_safe(f.jurisdiction),
                m.mapping_index,
                _csv_safe(m.category),
                _csv_safe(m.case_type),
                _csv_safe(m.filing_type),
                _csv_safe(m.filing_phase),
                m.confidence,
                _csv_safe(m.catalog_status),
                _csv_safe(m.association_status),
                _csv_safe(v.reviewer_name),
                _csv_safe(v.verdict),
                _csv_safe(v.reviewer_notes),
                v.created_at.isoformat(),
                v.updated_at.isoformat(),
                _csv_safe(form_review.reviewed_title if form_review else ""),
                _csv_safe(form_review.title_verdict if form_review else ""),
                _csv_safe(form_review.reviewed_form_id if form_review else ""),
                _csv_safe(form_review.form_id_verdict if form_review else ""),
                _csv_safe(form_review.reviewer_notes if form_review else ""),
                _csv_safe(v.reviewed_category),
                _csv_safe(v.reviewed_case_type),
                _csv_safe(v.reviewed_filing_type),
                _csv_safe(json.dumps(v.field_verdicts, ensure_ascii=False, sort_keys=True)),
                _csv_safe(json.dumps(v.lookup_context, ensure_ascii=False, sort_keys=True)),
            ]
        )

    return response


@require_GET
def export_json(request):
    """Download the complete crosswalk review state, including identity-only forms."""
    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "crosswalk_review_endpoint": REVIEW_EFSP_URL,
        "forms": [],
    }
    forms = CrosswalkForm.objects.prefetch_related("mappings__verdicts", "reviews").order_by(
        "registry_index", "canonical_id"
    )
    for form in forms:
        form_data = {
            "canonical_id": form.canonical_id,
            "jurisdiction": form.jurisdiction,
            "assigned_title": form.canonical_name,
            "assigned_form_id": form.form_id,
            "source_urls": form.source_urls,
            "is_form": form.is_form,
            "is_efileable": form.is_efileable,
            "reviews": [],
            "mappings": [],
        }
        for review in _related_objects(form, "reviews"):
            form_data["reviews"].append(
                {
                    "reviewer_name": review.reviewer_name,
                    "reviewed_title": review.reviewed_title,
                    "title_verdict": review.title_verdict,
                    "reviewed_form_id": review.reviewed_form_id,
                    "form_id_verdict": review.form_id_verdict,
                    "reviewer_notes": review.reviewer_notes,
                    "created_at": review.created_at.isoformat(),
                    "updated_at": review.updated_at.isoformat(),
                }
            )
        for mapping in sorted(_related_objects(form, "mappings"), key=lambda item: item.mapping_index):
            mapping_data = {
                "mapping_index": mapping.mapping_index,
                "assigned": {
                    "category": mapping.category,
                    "case_type": mapping.case_type,
                    "filing_type": mapping.filing_type,
                    "filing_phase": mapping.filing_phase,
                    "court_names": mapping.court_names,
                },
                "reviews": [],
            }
            for verdict in _related_objects(mapping, "verdicts"):
                mapping_data["reviews"].append(
                    {
                        "reviewer_name": verdict.reviewer_name,
                        "verdict": verdict.verdict,
                        "reviewed_category": verdict.reviewed_category,
                        "reviewed_case_type": verdict.reviewed_case_type,
                        "reviewed_filing_type": verdict.reviewed_filing_type,
                        "field_verdicts": verdict.field_verdicts,
                        "lookup_context": verdict.lookup_context,
                        "reviewer_notes": verdict.reviewer_notes,
                        "created_at": verdict.created_at.isoformat(),
                        "updated_at": verdict.updated_at.isoformat(),
                    }
                )
            form_data["mappings"].append(mapping_data)
        payload["forms"].append(form_data)
    response = JsonResponse(payload, json_dumps_params={"indent": 2})
    response["Content-Disposition"] = 'attachment; filename="crosswalk_review.json"'
    return response


def _csv_safe(value):
    """Prevent spreadsheet programs from interpreting exported text as formulas."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return f"'{value}"
    return value
