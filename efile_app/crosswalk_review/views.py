"""Views for the crosswalk_review app."""

import csv
import os

from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import CrosswalkForm, CrosswalkMapping, MappingVerdict

LITEFILE_BASE_URL = os.environ.get("LITEFILE_BASE_URL", "https://litefile-staging.fly.dev")


def _reviewer_from_request(request):
    """Extract reviewer name from POST, GET, or session."""
    reviewer = (
        request.POST.get("reviewer_name", "").strip()
        or request.GET.get("reviewer", "").strip()
        or request.session.get("reviewer_name", "").strip()
    )
    return reviewer


def index(request):
    """Landing page – reviewer enters name, sees progress stats."""
    reviewer = _reviewer_from_request(request)

    if request.method == "POST" and reviewer:
        request.session["reviewer_name"] = reviewer
        return redirect(reverse("crosswalk_review:next_unreviewed") + f"?reviewer={reviewer}")

    # Stats
    total_forms = CrosswalkForm.objects.count()
    total_mappings = CrosswalkMapping.objects.count()
    total_verdicts = MappingVerdict.objects.count()

    # Forms where every mapping has at least one verdict (by any reviewer)
    forms_fully_reviewed = (
        CrosswalkForm.objects.annotate(
            mapping_count=Count("mappings", distinct=True),
            verdict_count=Count("mappings__verdicts", distinct=True),
        )
        .filter(mapping_count__gt=0, verdict_count__gte=1)
        .count()
    )

    reviewer_stats = []
    if reviewer:
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
        "reviewer_stats": reviewer_stats,
        "litefile_base_url": LITEFILE_BASE_URL,
    }
    return render(request, "crosswalk_review/index.html", context)


def review_form(request, canonical_id):
    """Show a form card with all its mappings and collect reviewer verdicts."""
    form_obj = get_object_or_404(CrosswalkForm.objects.prefetch_related("mappings"), canonical_id=canonical_id)
    reviewer = _reviewer_from_request(request)

    if not reviewer:
        return redirect(reverse("crosswalk_review:index"))

    # Persist reviewer name in session
    request.session["reviewer_name"] = reviewer

    mappings = list(form_obj.mappings.order_by("mapping_index"))

    if request.method == "POST":
        with transaction.atomic():
            for mapping in mappings:
                verdict_key = f"verdict_{mapping.pk}"
                notes_key = f"notes_{mapping.pk}"
                verdict_val = request.POST.get(verdict_key, "").strip()
                notes_val = request.POST.get(notes_key, "").strip()
                if verdict_val in ("correct", "incorrect", "unsure"):
                    MappingVerdict.objects.update_or_create(
                        mapping=mapping,
                        reviewer_name=reviewer,
                        defaults={"verdict": verdict_val, "reviewer_notes": notes_val},
                    )
        # Navigate to next unreviewed
        return redirect(reverse("crosswalk_review:next_unreviewed") + f"?reviewer={reviewer}")

    # Load existing verdicts by this reviewer
    existing_verdicts = {
        v.mapping_id: v for v in MappingVerdict.objects.filter(mapping__form=form_obj, reviewer_name=reviewer)
    }

    # Build mapping rows with context
    mapping_rows = []
    for mapping in mappings:
        court_names = mapping.court_names or []
        mapping_rows.append(
            {
                "obj": mapping,
                "court_names_display": ", ".join(court_names) if court_names else "—",
                "existing_verdict": existing_verdicts.get(mapping.pk),
                "browse_url": f"{LITEFILE_BASE_URL}/jurisdiction/{form_obj.jurisdiction}/options/",
            }
        )

    # Prev / Next navigation
    all_ids = list(CrosswalkForm.objects.values_list("canonical_id", flat=True).order_by("registry_index"))
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
    }
    return render(request, "crosswalk_review/review.html", context)


@require_GET
def next_unreviewed(request):
    """Redirect to the next form that has no verdict from this reviewer."""
    reviewer = request.GET.get("reviewer", "").strip() or request.session.get("reviewer_name", "").strip()
    if not reviewer:
        return redirect(reverse("crosswalk_review:index"))

    # Forms that have at least one mapping not yet reviewed by this reviewer
    reviewed_form_ids = set(
        MappingVerdict.objects.filter(reviewer_name=reviewer).values_list("mapping__form_id", flat=True).distinct()
    )

    # Find first form (by registry_index) not touched at all by this reviewer
    unreviewed = CrosswalkForm.objects.order_by("registry_index").exclude(canonical_id__in=reviewed_form_ids).first()

    if unreviewed:
        target_id = unreviewed.canonical_id
    else:
        # Fall back to the first form
        first = CrosswalkForm.objects.order_by("registry_index").first()
        target_id = first.canonical_id if first else None

    if not target_id:
        return redirect(reverse("crosswalk_review:index"))

    return redirect(reverse("crosswalk_review:review_form", args=[target_id]) + f"?reviewer={reviewer}")


@require_GET
def progress(request):
    """Summary page showing review progress per form and per reviewer."""
    reviewer = _reviewer_from_request(request)

    # Per-form stats: mapping count and verdict count (any reviewer)
    forms = CrosswalkForm.objects.annotate(
        mapping_count=Count("mappings", distinct=True),
        verdict_count=Count("mappings__verdicts", distinct=True),
    ).order_by("registry_index")

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
                f.canonical_id,
                f.canonical_name,
                f.jurisdiction,
                m.mapping_index,
                m.category,
                m.case_type,
                m.filing_type,
                m.filing_phase,
                m.confidence,
                m.catalog_status,
                m.association_status,
                v.reviewer_name,
                v.verdict,
                v.reviewer_notes,
                v.created_at.isoformat(),
                v.updated_at.isoformat(),
            ]
        )

    return response
