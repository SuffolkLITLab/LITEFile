from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import DocumentExtraction, FilingDocument
from efile.party_sides import PARTY_SIDE_HELP, PARTY_SIDE_LABELS, PartySide
from efile.services.current_drafts import ensure_current_draft
from efile.services.document_checklists import resolve_filer_roles
from efile.services.document_extractions import extraction_for_document
from efile.services.drafts import draft_snapshot, write_case_data
from efile.services.extracted_parties import review_rows, save_reviewed_parties
from efile.services.extraction_fields import display_extracted_fields, document_summary_details
from efile.services.filing_path import change_filing_path, describe_path_change, filing_path_conflict
from efile.workflow import (
    RETURN_TO_REVIEW,
    ExistingCase,
    WorkflowStepKey,
    get_next_step,
    get_step_url,
    get_workflow_context,
)


def _offered_filer_roles(request, jurisdiction):
    """The sides on offer for the case the filer is choosing right now.

    Resolved from what was submitted rather than from the draft: the case type
    on this screen is not saved until the form is, and a role only means
    something against the case it was offered for.
    """

    return resolve_filer_roles(
        jurisdiction=jurisdiction,
        court_code=request.POST.get("court_code", ""),
        case_category_name=request.POST.get("case_category_name", ""),
        case_type_name=request.POST.get("case_type_name", ""),
        lead_filing_type_name=request.POST.get("filing_type_name", ""),
    )


def _submitted_party_rows(request):
    """Read the party editor back off the form, keeping its rows aligned.

    Every row posts all of its inputs, including the empty id of a row the
    filer just added, so the lists stay index-aligned even when rows were
    added or removed in the browser.
    """

    ids = request.POST.getlist("party_id")
    names = request.POST.getlist("party_name")
    sides = request.POST.getlist("party_side")
    hints = request.POST.getlist("party_role_hint")
    # A hidden value rather than a checkbox, so an unticked row still posts
    # something and the lists stay index-aligned with the names beside them.
    selves = request.POST.getlist("party_is_self")
    rows = []
    for index, name in enumerate(names):
        raw_id = ids[index] if index < len(ids) else ""
        rows.append(
            {
                "id": int(raw_id) if str(raw_id).isdigit() else None,
                "name": name,
                "side": sides[index] if index < len(sides) else "",
                "role_hint": hints[index] if index < len(hints) else "",
                "is_self": selves[index] if index < len(selves) else "",
            }
        )
    return rows


def _set_lead_filing_type(draft, filing_type_code, filing_type_name):
    if not filing_type_code:
        return
    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    if lead is None:
        return
    lead.filing_type_code = filing_type_code
    lead.filing_type_name = filing_type_name
    lead.save(update_fields=["filing_type_code", "filing_type_name", "updated_at"])


def _case_identity(existing_case, docket_number):
    """The case number and title this screen may save.

    A new case has neither until the court opens it, so both are cleared (and
    a number would make Tyler treat the filing as subsequent). An existing
    case's number is only a search term for the case lookup; its title is left
    alone, because the court sets it when the case is found.
    """
    if existing_case == ExistingCase.NEW:
        return {"docket_number": "", "case_title": ""}
    return {"docket_number": docket_number}


@require_http_methods(["GET", "POST"])
def extraction_review(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.EXTRACTION_REVIEW,
        workflow_version=2,
    )
    if not FilingDocument.objects.filter(draft=draft).exists():
        messages.error(request, "Upload at least one document before reviewing the filing.")
        return redirect("upload_documents", jurisdiction=jurisdiction)

    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    extraction = extraction_for_document(lead) if lead else None
    if extraction is not None and extraction.status in {
        DocumentExtraction.Status.PENDING,
        DocumentExtraction.Status.PROCESSING,
    }:
        messages.info(request, "We are still analyzing your first PDF. You can leave this page and come back.")
        return redirect("upload_documents", jurisdiction=jurisdiction)

    # What the party editor should show: what was just submitted, so a filer
    # sent back to fix a validation error keeps the names they typed, and
    # otherwise what is saved (falling back to what the document named).
    party_rows = _submitted_party_rows(request) if request.method == "POST" else review_rows(draft)

    # The acknowledgement is only asked for when the page shows something to
    # acknowledge, so the check below and the template both key off this.
    guesses = display_extracted_fields(draft.extracted_guesses or {})
    needs_acknowledgement = bool(guesses)
    acknowledgement_error = False

    if request.method == "POST":
        existing_case = request.POST.get("existing_case", draft.existing_case)
        court_code = request.POST.get("court_code", "")
        case_category_code = request.POST.get("case_category_code", "")
        case_type_code = request.POST.get("case_type_code", "")

        offered_roles = {role["id"] for role in _offered_filer_roles(request, jurisdiction)}
        filer_role = request.POST.get("filer_role", "")

        if needs_acknowledgement and request.POST.get("reviewed_extraction") != "yes":
            # Shown beside the checkbox rather than as a toast, so it stays put
            # and is tied to the control that needs attention.
            acknowledgement_error = True
        elif existing_case not in {ExistingCase.NEW, ExistingCase.EXISTING}:
            messages.error(request, "Choose whether this is a new or existing court case to continue.")
        elif existing_case == ExistingCase.NEW and not (court_code and case_category_code and case_type_code):
            # Tyler's e-filing API only accepts exact court/category/type codes, so
            # a new case can't proceed on free-text guesses -- unlike an existing
            # case, which resolves these from the case lookup step instead.
            messages.error(request, "Choose a court, case category, and case type from the lists to continue.")
        elif offered_roles and filer_role not in offered_roles:
            # This case type means two different jobs, and the documents follow
            # the side rather than the case, so there is nothing to show until
            # the filer says which side is theirs.
            messages.error(request, "Choose which side of this case you are on to continue.")
        else:
            if offered_roles and draft.filer_role != filer_role:
                draft.filer_role = filer_role
                draft.save(update_fields=["filer_role", "updated_at"])
            # Before the rest is saved: switching kinds of filing clears the
            # filing types chosen for the old kind, and the lead's new one is
            # set from this form just below.
            path_change = change_filing_path(draft, existing_case)
            if path_change.changed and path_change.cleared:
                messages.info(request, describe_path_change(path_change))
            write_case_data(
                draft,
                {
                    "existing_case": existing_case,
                    "court": court_code,
                    "court_name": request.POST.get("court_name", ""),
                    "case_category": case_category_code,
                    "case_category_name": request.POST.get("case_category_name", ""),
                    "case_type": case_type_code,
                    "case_type_name": request.POST.get("case_type_name", ""),
                    **_case_identity(existing_case, request.POST.get("docket_number", "")),
                },
                current_step=WorkflowStepKey.EXTRACTION_REVIEW,
            )
            _set_lead_filing_type(
                draft,
                request.POST.get("filing_type_code", ""),
                request.POST.get("filing_type_name", ""),
            )
            # The people the document named, as the filer has now corrected
            # them. They are stored as sides here; the party screen turns each
            # side into this court's own party type once the case type it
            # depends on has been saved just above.
            save_reviewed_parties(draft, party_rows)
            # A different kind of filing is not an edit Review can take back
            # as-is: an existing case has to be found in the court's records,
            # and the documents need their filing types again. Only an
            # unchanged path, with any existing case already found, returns.
            returns_to_review = (
                request.POST.get("return_to") == RETURN_TO_REVIEW
                and not path_change.switched
                and not (existing_case == ExistingCase.EXISTING and not draft.previous_case_id)
            )
            if returns_to_review:
                write_case_data(draft, {}, current_step=WorkflowStepKey.REVIEW)
                return redirect(get_step_url(WorkflowStepKey.REVIEW, jurisdiction))
            next_step = get_next_step(WorkflowStepKey.EXTRACTION_REVIEW, draft)
            if next_step:
                write_case_data(draft, {}, current_step=next_step.key)
                return redirect(get_step_url(next_step.key, jurisdiction))

    classification = extraction.classification if extraction is not None else {}

    def classified(level, key):
        selection = classification.get(level, {}) if isinstance(classification, dict) else {}
        return selection.get(key, "") if selection.get("status") == "selected" else ""

    # Only what identifies the document is shown as read-only text. Anything
    # else the extraction found is either asked for by the form below, where
    # the filer can correct it, or not used by the filing at all, so it is not
    # shown.
    summary_details = document_summary_details(guesses)
    party_side_options = [
        {"value": str(side), "label": PARTY_SIDE_LABELS[side], "help": PARTY_SIDE_HELP[side]} for side in PartySide
    ]
    extraction_context = {
        "jurisdiction": jurisdiction,
        "guesses": guesses,
        "existing_case": draft.existing_case,
        "court_code": draft.court_code or classified("court", "route_key"),
        "court_name": draft.court_name or classified("court", "name"),
        "case_category_code": draft.case_category_code or classified("case category", "route_key"),
        "case_category_name": draft.case_category_name or classified("case category", "name"),
        "case_type_code": draft.case_type_code or classified("case type", "route_key"),
        "case_type_name": draft.case_type_name or classified("case type", "name"),
        "filing_type_code": (lead.filing_type_code if lead else "") or classified("filing type", "route_key"),
        "filing_type_name": (lead.filing_type_name if lead else "") or classified("filing type", "name"),
        # Only some case types have sides. The screen asks for one as soon as
        # the chosen case type turns out to be one of them.
        "filer_role": draft.filer_role,
    }
    suggested_existing_case = (
        "new"
        if not draft.existing_case and (extraction.evidence if extraction else {}).get("filing phase") == "initial"
        else "existing"
        if not draft.existing_case and (extraction.evidence if extraction else {}).get("filing phase") == "subsequent"
        else ""
    )
    chosen_existing_case = draft.existing_case or suggested_existing_case
    # The answer already given, shown as an answer with Change rather than
    # asked again. "Not sure" is not an answer to show, so it is still asked.
    saved_path = draft.existing_case if draft.existing_case in {ExistingCase.NEW, ExistingCase.EXISTING} else ""
    docket_number = draft.docket_number or guesses.get("docket number")
    if request.method == "POST":
        # Sent back to fix something: show what the filer submitted, not what
        # was saved before, so no answer has to be entered twice.
        for key in (
            "court_code",
            "court_name",
            "case_category_code",
            "case_category_name",
            "case_type_code",
            "case_type_name",
            "filing_type_code",
            "filing_type_name",
            "filer_role",
        ):
            extraction_context[key] = request.POST.get(key, "")
        chosen_existing_case = request.POST.get("existing_case", "")
        docket_number = request.POST.get("docket_number", "")
        extraction_context["existing_case"] = chosen_existing_case
    # Against the answer on screen, which after a refused POST is the one
    # submitted rather than the one saved.
    path_conflict = filing_path_conflict(
        draft,
        extraction.evidence if extraction else {},
        document_title=guesses.get("document title", ""),
        chosen=chosen_existing_case,
    )
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "has_guesses": needs_acknowledgement,
        "document_summary_details": summary_details,
        "party_rows": party_rows,
        "party_side_options": party_side_options,
        "extraction_failed": extraction is not None and extraction.status == DocumentExtraction.Status.FAILED,
        # The filer turned AI off for this filing, so the details below came
        # from a keyword scan of the document's own text. The screen says so
        # rather than crediting a reading that never happened.
        "ai_opted_out": draft.ai_assistance_opted_out,
        "extraction_pages_analyzed": extraction.pages_analyzed if extraction else None,
        "extraction_total_pages": extraction.total_pages if extraction else None,
        "classification": classification,
        "chosen_existing_case": chosen_existing_case,
        "saved_path": saved_path,
        "path_conflict": path_conflict,
        # Open when there is no saved answer to show, or when the filer was
        # sent back with a different answer than the saved one.
        "path_question_open": not saved_path or chosen_existing_case != saved_path,
        "docket_number": docket_number,
        "needs_acknowledgement": needs_acknowledgement,
        "acknowledgement_error": acknowledgement_error,
        "reviewed_extraction": request.method == "POST" and request.POST.get("reviewed_extraction") == "yes",
        "extraction_context": extraction_context,
        "return_to": request.GET.get("return_to", ""),
    }
    context.update(get_workflow_context(WorkflowStepKey.EXTRACTION_REVIEW, jurisdiction, draft))
    return render(request, "efile/extraction_review.html", context)
