from django.contrib import messages
from django.shortcuts import redirect, render

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDraft
from efile.services.current_drafts import resolve_explicit_draft

from ..workflow import WorkflowStepKey, get_workflow_context

LAST_SUBMITTED_DRAFT_SESSION_KEY = "last_submitted_filing_draft_id"


def _confirmation_number(response):
    if isinstance(response, dict):
        for key in ("confirmation_number", "confirmationNumber", "filing_id", "filingId", "id"):
            if response.get(key):
                return str(response[key])
        values = response.values()
    elif isinstance(response, list):
        values = response
    else:
        return ""
    for value in values:
        found = _confirmation_number(value)
        if found:
            return found
    return ""


def filing_confirmation(request, jurisdiction):
    """Show the submitted durable draft and external confirmation reference."""
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    submitted = FilingDraft.objects.filter(
        user=request.user,
        jurisdiction=jurisdiction,
        status=FilingDraft.Status.SUBMITTED,
    )
    draft = resolve_explicit_draft(request, jurisdiction=jurisdiction, statuses=(FilingDraft.Status.SUBMITTED,))
    draft_id = request.session.get(LAST_SUBMITTED_DRAFT_SESSION_KEY)
    if draft is None:
        draft = submitted.filter(pk=draft_id).first() if draft_id else None
    if draft is None:
        draft = submitted.order_by("-submitted_at", "-updated_at").first()
    if draft is None:
        messages.info(request, "No submitted filing was found for this confirmation page.")
        return redirect("filing_statuses", jurisdiction=jurisdiction)
    request.filing_draft = draft
    context = {
        "is_logged_in": True,
        "page_title": "Filing confirmation",
        "draft": draft,
        "confirmation_number": _confirmation_number(draft.submission_response),
    }
    context.update(get_workflow_context(WorkflowStepKey.CONFIRMATION, jurisdiction, draft))
    return render(request, "efile/confirmation.html", context)
