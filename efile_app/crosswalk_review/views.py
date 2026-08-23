"""Views for the crosswalk_review app."""

import csv
import os
from urllib.parse import urlencode

from django.db import transaction
from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from .models import CrosswalkForm, CrosswalkMapping, MappingVerdict

LITEFILE_BASE_URL = os.environ.get("LITEFILE_BASE_URL", "https://litefile-staging.fly.dev")
MAX_REVIEWER_NAME_LENGTH = MappingVerdict._meta.get_field("reviewer_name").max_length
VERDICTS = {choice[0] for choice in MappingVerdict.VERDICT_CHOICES}


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


def _reviewer_url(url_name, reviewer, *, args=None):
    """Build an internal URL with a safely encoded reviewer query parameter."""
    return f"{reverse(url_name, args=args)}?{urlencode({'reviewer': reviewer})}"


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
        return redirect(_reviewer_url("crosswalk_review:next_unreviewed", reviewer))

    # Stats
    total_forms = CrosswalkForm.objects.count()
    total_mappings = CrosswalkMapping.objects.count()
    total_verdicts = MappingVerdict.objects.count()

    # Forms where every mapping has at least one verdict (by any reviewer)
    forms_fully_reviewed = (
        _forms_with_review_counts()
        .filter(
            mapping_count__gt=0,
            reviewed_mapping_count=F("mapping_count"),
        )
        .count()
    )
    overall_progress_percent = round(forms_fully_reviewed / total_forms * 100) if total_forms else 0

    reviewer_stats = []
    if reviewer and not reviewer_error:
        my_verdict_count = MappingVerdict.objects.filter(reviewer_name=reviewer).count()
        # Count distinct forms this reviewer has submitted at least one verdict for
        my_forms_touched = CrosswalkForm.objects.filter(mappings__verdicts__reviewer_name=reviewer).distinct().count()
        reviewer_stats = {
            "name": reviewer,
            "verdicts": my_verdict_count,
            "forms_touched": my_forms_touched,
        }

    context = {
        "reviewer": reviewer,
        "total_forms": total_forms,
        "total_mappings": total_mappings,
        "total_verdicts": total_verdicts,
        "forms_fully_reviewed": forms_fully_reviewed,
        "overall_progress_percent": overall_progress_percent,
        "reviewer_stats": reviewer_stats,
        "reviewer_error": reviewer_error,
        "litefile_base_url": LITEFILE_BASE_URL,
    }
    return render(request, "crosswalk_review/index.html", context)


@require_http_methods(["GET", "POST"])
def review_form(request, canonical_id):
    """Show a form card with all its mappings and collect reviewer verdicts."""
    form_obj = get_object_or_404(CrosswalkForm.objects.prefetch_related("mappings"), canonical_id=canonical_id)
    reviewer = _reviewer_from_request(request)

    if not reviewer or len(reviewer) > MAX_REVIEWER_NAME_LENGTH:
        target = reverse("crosswalk_review:index")
        if reviewer:
            target = f"{target}?{urlencode({'reviewer': reviewer})}"
        return redirect(target)

    # Persist reviewer name in session
    request.session["reviewer_name"] = reviewer

    mappings = list(form_obj.mappings.order_by("mapping_index"))

    submission_error = ""
    if request.method == "POST":
        submitted_verdicts = {mapping.pk: request.POST.get(f"verdict_{mapping.pk}", "").strip() for mapping in mappings}
        invalid_mappings = [mapping for mapping in mappings if submitted_verdicts[mapping.pk] not in VERDICTS]
        if invalid_mappings:
            submission_error = "Choose a verdict for every mapping before continuing."
        else:
            with transaction.atomic():
                for mapping in mappings:
                    MappingVerdict.objects.update_or_create(
                        mapping=mapping,
                        reviewer_name=reviewer,
                        defaults={
                            "verdict": submitted_verdicts[mapping.pk],
                            "reviewer_notes": request.POST.get(f"notes_{mapping.pk}", "").strip(),
                        },
                    )
            return redirect(_reviewer_url("crosswalk_review:next_unreviewed", reviewer))

    # Load existing verdicts by this reviewer. On a rejected POST, redisplay the
    # submitted values so the reviewer only has to fill in missing answers.
    existing_verdicts = {
        v.mapping_id: v for v in MappingVerdict.objects.filter(mapping__form=form_obj, reviewer_name=reviewer)
    }
    mapping_rows = []
    for mapping in mappings:
        existing = existing_verdicts.get(mapping.pk)
        selected_verdict = existing.verdict if existing else ""
        reviewer_notes = existing.reviewer_notes if existing else ""
        if request.method == "POST":
            selected_verdict = request.POST.get(f"verdict_{mapping.pk}", "").strip()
            reviewer_notes = request.POST.get(f"notes_{mapping.pk}", "").strip()
        court_names = mapping.court_names or []
        mapping_rows.append(
            {
                "obj": mapping,
                "court_names_display": ", ".join(court_names) if court_names else "—",
                "selected_verdict": selected_verdict,
                "reviewer_notes": reviewer_notes,
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
        "submission_error": submission_error,
    }
    return render(request, "crosswalk_review/review.html", context)


@require_GET
def next_unreviewed(request):
    """Redirect to the next form with a mapping this reviewer has not reviewed."""
    reviewer = _reviewer_from_request(request)
    if not reviewer or len(reviewer) > MAX_REVIEWER_NAME_LENGTH:
        return redirect(reverse("crosswalk_review:index"))

    request.session["reviewer_name"] = reviewer
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
    forms = (
        _forms_with_review_counts()
        .annotate(
            verdict_count=Count("mappings__verdicts", distinct=True),
        )
        .order_by("registry_index", "canonical_id")
    )

    # Per-reviewer totals
    reviewer_totals = MappingVerdict.objects.values("reviewer_name").annotate(total=Count("id")).order_by("-total")

    context = {
        "forms": forms,
        "reviewer_totals": reviewer_totals,
        "reviewer": reviewer,
        "total_forms": CrosswalkForm.objects.count(),
        "total_verdicts": MappingVerdict.objects.count(),
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
        ]
    )

    verdicts = MappingVerdict.objects.select_related("mapping__form").order_by(
        "mapping__form__canonical_id", "mapping__mapping_index", "reviewer_name"
    )

    for v in verdicts:
        m = v.mapping
        f = m.form
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
            ]
        )

    return response


def _csv_safe(value):
    """Prevent spreadsheet programs from interpreting exported text as formulas."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return f"'{value}"
    return value
