from django.contrib import messages
from django.shortcuts import redirect, render

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument, FilingParty
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, read_case_data, read_upload_data
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
        "documents": FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "created_at"),
        "question_answers": question_answers,
    }
    context.update(get_workflow_context(WorkflowStepKey.REVIEW, jurisdiction, draft))
    return render(request, "efile/review.html", context)
