"""Owner-checked, durable destinations for filing notifications."""

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from efile.models import FilingDraft
from efile.services.handoff import same_filer
from efile.utils.jurisdiction_stuff import has_jurisdiction_login, redirect_to_jurisdiction_login


@require_http_methods(["GET"])
def submission_tracker(request, public_id):
    if not request.user.is_authenticated:
        # Sign-in is per jurisdiction, so read only that. The ID is a random
        # UUID: a signed-out visitor can't use this to find submissions.
        jurisdiction = FilingDraft.objects.filter(public_id=public_id).values_list("jurisdiction", flat=True).first()
        if jurisdiction is None:
            raise Http404
        return redirect_to_jurisdiction_login(request, jurisdiction)
    draft = get_object_or_404(
        FilingDraft.objects.select_related("user").only(
            "pk",
            "jurisdiction",
            "court_code",
            "user__tyler_user_id",
            "user__tyler_username",
            "user__tyler_jurisdiction",
        ),
        public_id=public_id,
    )
    # Signed in elsewhere: offer the right sign-in, as for a signed-out visitor.
    if not has_jurisdiction_login(request, draft.jurisdiction):
        return redirect_to_jurisdiction_login(request, draft.jurisdiction)
    # Check ownership before making any court request or exposing filing data.
    if not same_filer(request.user, draft.user):
        raise Http404
    filing_ids = sorted(draft.filing_identifiers.values_list("filing_id", flat=True))
    selected = request.GET.get("filing_id")
    if selected and selected not in filing_ids:
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
