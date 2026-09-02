from django.contrib import messages
from django.shortcuts import redirect, render

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument, FilingParty
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, read_case_data, read_upload_data
from efile.services.extracted_parties import party_display_name
from efile.services.filing_plans import documents_missing_from_envelope
from efile.services.people import get_case_questions

from ..workflow import WorkflowStepKey, get_workflow_context


def case_review(request, jurisdiction):
    """Render a single read-only summary from the durable draft before submit."""
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.REVIEW,
        workflow_version=2,
    )
    if not draft.selected_payment_account_id:
        messages.error(request, "Choose a payment method before reviewing your filing.")
        return redirect("payment", jurisdiction=jurisdiction)

    question_labels = {question["name"]: question["label"] for question in get_case_questions(draft)}
    question_answers = [
        {
            "label": question_labels.get(key, key.replace("_", " ").title()),
            "value": "Yes" if value is True else "No" if value is False else value,
        }
        for key, value in (draft.supplemental_fields or {}).items()
        if not key.startswith("_") and value not in (None, "")
    ]
    parties = FilingParty.objects.filter(draft=draft)
    context = {
        "is_logged_in": True,
        "case_data": read_case_data(draft),
        "upload_data": read_upload_data(draft),
        "filing_draft": draft_snapshot(draft),
        "draft": draft,
        "filer": parties.filter(role="filer").first(),
        "parties": parties.exclude(role="filer").order_by("sort_order", "created_at"),
        # Who the filing is on behalf of, when that is not the filer. Worth
        # saying out loud on the last screen before submission: a filing sent
        # under the wrong party's name is not something the filer can undo.
        "filing_for": [
            party_display_name(party)
            for party in parties.filter(is_filing_party=True).exclude(role="filer").order_by("sort_order", "created_at")
        ],
        # Only shown when it was actually asked for. A filer who is a party in
        # their own case is reached at their account address, and saying so
        # here would be one more line of screen for nothing.
        "notice_email": draft.notice_email,
        "documents": FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "created_at"),
        "question_answers": question_answers,
        # Everything in one envelope reaches the clerk together. This is the
        # last point at which adding a document is still free and easy, so say
        # what the filer's own plan expects and this envelope does not have.
        "plan_missing_documents": documents_missing_from_envelope(draft.plan, draft),
    }
    context.update(get_workflow_context(WorkflowStepKey.REVIEW, jurisdiction, draft))
    return render(request, "efile/review.html", context)
