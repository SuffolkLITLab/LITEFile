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


def _matches_extracted_value(current, extracted, exact=False):
    """Return whether a saved value is still the value extraction suggested.

    Pass exact=True for short values where one character is the whole meaning: a
    filer who corrects docket 2026-CV-1234 to 2026-CV-123 has not left our guess
    in place, and the marker would tell them their document said otherwise.
    """
    current_text = " ".join(str(current or "").casefold().split())
    extracted_text = " ".join(str(extracted or "").casefold().split())
    if not current_text or not extracted_text:
        return False
    if exact:
        return current_text == extracted_text
    return (
        current_text == extracted_text
        or (len(extracted_text) >= 4 and extracted_text in current_text)
        or (len(current_text) >= 4 and current_text in extracted_text)
    )


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
    parties = list(FilingParty.objects.filter(draft=draft).order_by("sort_order", "created_at"))
    filer = next((party for party in parties if party.role == "filer"), None)
    other_parties = [party for party in parties if party.role != "filer"]
    documents = FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "created_at")
    extracted_guesses = draft.extracted_guesses or {}
    extracted_party_text = "; ".join(
        str(extracted_guesses.get(key, ""))
        for key in ("plaintiff or petitioner names", "defendant or respondent names", "other party names")
    )
    extracted_markers = {
        "case_title": _matches_extracted_value(draft.case_title, extracted_guesses.get("case title")),
        "docket_number": _matches_extracted_value(
            draft.docket_number, extracted_guesses.get("docket number"), exact=True
        ),
        "court": _matches_extracted_value(draft.court_name, extracted_guesses.get("court")),
        "case_category": _matches_extracted_value(draft.case_category_name, extracted_guesses.get("case category")),
        "case_type": _matches_extracted_value(draft.case_type_name, extracted_guesses.get("case type")),
        "party_ids": {
            party.id for party in parties if _matches_extracted_value(party_display_name(party), extracted_party_text)
        },
        "document_ids": {
            document.id
            for document in documents
            if _matches_extracted_value(document.filing_type_name, extracted_guesses.get("filing type"))
        },
    }
    extracted_markers["has_any"] = any(
        value for key, value in extracted_markers.items() if key not in {"document_ids", "party_ids"}
    ) or bool(extracted_markers["document_ids"] or extracted_markers["party_ids"])
    context = {
        "is_logged_in": True,
        "case_data": read_case_data(draft),
        "upload_data": read_upload_data(draft),
        "filing_draft": draft_snapshot(draft),
        "draft": draft,
        "filer": filer,
        "parties": other_parties,
        # Who the filing is on behalf of, when that is not the filer. Worth
        # saying out loud on the last screen before submission: a filing sent
        # under the wrong party's name is not something the filer can undo.
        "filing_for": [party_display_name(party) for party in other_parties if party.is_filing_party],
        # Only shown when it was actually asked for. A filer who is a party in
        # their own case is reached at their account address, and saying so
        # here would be one more line of screen for nothing.
        "notice_email": draft.notice_email,
        "documents": documents,
        "extracted_markers": extracted_markers,
        "question_answers": question_answers,
        # Everything in one envelope reaches the clerk together. This is the
        # last point at which adding a document is still free and easy, so say
        # what the filer's own plan expects and this envelope does not have.
        "plan_missing_documents": documents_missing_from_envelope(draft.plan, draft),
    }
    context.update(get_workflow_context(WorkflowStepKey.REVIEW, jurisdiction, draft))
    return render(request, "efile/review.html", context)
