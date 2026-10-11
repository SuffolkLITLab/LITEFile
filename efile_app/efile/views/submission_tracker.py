"""Owner-checked, durable destinations for filing notifications."""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from efile.models import FilingDraft
from efile.services.handoff import submitted_filing_ids
from efile.utils.jurisdiction_stuff import has_jurisdiction_login


@require_http_methods(["GET"])
def submission_tracker(request, submission_reference):
    draft = get_object_or_404(FilingDraft, pk=submission_reference)
    if not request.user.is_authenticated:
        return redirect(
            reverse("efile_login", kwargs={"jurisdiction": draft.jurisdiction})
            + "?"
            + urlencode({"next": request.get_full_path()})
        )
    # Check ownership before making any court request or exposing filing data.
    draft = get_object_or_404(FilingDraft, pk=submission_reference, user=request.user)
    if not has_jurisdiction_login(request, draft.jurisdiction):
        return redirect(
            reverse("efile_login", kwargs={"jurisdiction": draft.jurisdiction})
            + "?"
            + urlencode({"next": request.get_full_path()})
        )
    filing_ids = sorted(submitted_filing_ids(draft.submission_response))
    selected = request.GET.get("filing_id")
    if selected and selected not in filing_ids:
        from django.http import Http404

        raise Http404
    if selected or len(filing_ids) == 1:
        return redirect(
            "filing_detail",
            jurisdiction=draft.jurisdiction,
            court_code=draft.court_code,
            filing_id=selected or filing_ids[0],
        )
    return render(
        request,
        "efile/submission_tracker.html",
        {
            "draft": draft,
            "filing_ids": filing_ids,
            "jurisdiction": draft.jurisdiction,
        },
    )
