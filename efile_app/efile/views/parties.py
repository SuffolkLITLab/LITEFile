from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingParty
from efile.party_sides import PARTY_SIDE_LABELS
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.extracted_parties import party_display_name
from efile.services.people import (
    NOT_A_PARTY,
    absorb_filer_duplicates,
    apply_party_sides,
    claim_party_as_filer,
    discard_empty_parties,
    ensure_required_parties,
    filer_name_match,
    filing_party_candidates,
    get_case_questions,
    get_party_types,
    guess_filer_party_type,
    incomplete_parties,
    needs_amount_in_controversy,
    party_is_complete,
    set_filing_parties,
)
from efile.workflow import RETURN_TO_REVIEW, WorkflowStepKey, get_step_url, get_workflow_context, with_return_to


def _party_details_url(jurisdiction, party, return_to=None):
    url = f"{reverse('party_details', kwargs={'jurisdiction': jurisdiction})}?party={party.pk}"
    return with_return_to(url, return_to)


def _parties_url(jurisdiction, return_to=None):
    return with_return_to(reverse("parties", kwargs={"jurisdiction": jurisdiction}), return_to)


def _is_email(value):
    try:
        validate_email(value)
    except ValidationError:
        return False
    return True


def _chosen_filing_parties(request, draft):
    """The roster rows the filer ticked as the people they are filing for."""

    ids = [value for value in request.POST.getlist("filing_for") if str(value).isdigit()]
    if not ids:
        return []
    return list(FilingParty.objects.filter(draft=draft, role="other", pk__in=ids))


def _continue_from_parties(request, jurisdiction, draft, party_types, return_to):
    """Fill in the court's required parties, then move on or collect the gaps."""

    ensure_required_parties(draft, party_types)
    incomplete = incomplete_parties(draft, party_types=party_types)
    if incomplete:
        draft.current_step = WorkflowStepKey.PARTY_DETAILS
        draft.save(update_fields=["current_step", "updated_at"])
        return redirect(_party_details_url(jurisdiction, incomplete[0], return_to))

    has_questions = bool(get_case_questions(draft)) or needs_amount_in_controversy(draft)
    draft.supplemental_fields = {
        **(draft.supplemental_fields or {}),
        "_case_questions_required": has_questions,
    }
    if return_to == RETURN_TO_REVIEW:
        draft.current_step = WorkflowStepKey.REVIEW
    else:
        draft.current_step = WorkflowStepKey.CASE_QUESTIONS if has_questions else WorkflowStepKey.PAYMENT
    draft.save(update_fields=["supplemental_fields", "current_step", "updated_at"])
    return redirect(get_step_url(draft.current_step, jurisdiction))


@require_http_methods(["GET", "POST"])
def parties(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.PARTIES,
        workflow_version=2,
    )
    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    if filer is None:
        return redirect("your_information", jurisdiction=jurisdiction)
    party_types = get_party_types(draft)
    party_type_names = {item["code"]: item["name"] for item in party_types}
    # A person the filer started adding and never named is not a party they
    # meant to add, and reaches this list as an entry they cannot tell apart
    # from one they did. Only ever cleared on the way in: a POST is somebody
    # acting on a row, including the blank one they just made.
    if request.method == "GET":
        discard_empty_parties(draft)
    # The document said which side each person is on; the case type -- settled
    # by now -- says what this court calls that side. Folding the filer's own
    # duplicate in first keeps them from reaching the court twice.
    absorb_filer_duplicates(draft)
    apply_party_sides(draft, party_types)

    if request.method == "POST":
        action = request.POST.get("action", "continue")
        return_to = request.POST.get("return_to")
        if action == "add":
            last_order = (
                FilingParty.objects.filter(draft=draft, role="other")
                .order_by("-sort_order")
                .values_list("sort_order", flat=True)
                .first()
            )
            party = FilingParty.objects.create(
                draft=draft,
                role="other",
                sort_order=0 if last_order is None else last_order + 1,
            )
            draft.current_step = WorkflowStepKey.PARTY_DETAILS
            draft.save(update_fields=["current_step", "updated_at"])
            return redirect(_party_details_url(jurisdiction, party, return_to))
        if action == "claim_party":
            # "That party is me." Said of a person the document named, or of
            # the blank row someone started before realising they were adding
            # themselves. Either way the filer is already on this draft with a
            # name and an address, so the other row goes rather than reaching
            # the court as a second person.
            party = get_object_or_404(FilingParty, pk=request.POST.get("party_id"), draft=draft, role="other")
            claim_party_as_filer(draft, party)
            filer.refresh_from_db()
            if filer.party_type:
                messages.success(
                    request,
                    f"You are listed in this case as the {filer.party_type_name or filer.party_type}.",
                )
            else:
                messages.success(request, "Choose your own role below to add yourself as a party.")
            return redirect(f"{_parties_url(jurisdiction, return_to)}#your-role")
        if action == "remove":
            party = get_object_or_404(FilingParty, pk=request.POST.get("party_id"), draft=draft, role="other")
            party.delete()
            messages.success(request, "Party removed.")
            return redirect(_parties_url(jurisdiction, return_to))

        filer_type = request.POST.get("filer_party_type", "").strip()
        if filer_type == NOT_A_PARTY:
            # Filing for someone else. Tyler still needs a party to file on
            # behalf of, so the filer names one instead of becoming one.
            chosen = _chosen_filing_parties(request, draft)
            notice_email = request.POST.get("notice_email", "").strip()
            if not chosen:
                messages.error(request, "Choose who you are filing for.")
            elif not _is_email(notice_email):
                messages.error(request, "Give an email address for notices about this case.")
            else:
                filer.party_type = ""
                filer.party_type_name = ""
                filer.save(update_fields=["party_type", "party_type_name", "updated_at"])
                set_filing_parties(draft, chosen)
                draft.notice_email = notice_email
                draft.save(update_fields=["notice_email", "updated_at"])
                return _continue_from_parties(request, jurisdiction, draft, party_types, return_to)
        elif filer_type in party_type_names:
            filer.party_type = filer_type
            filer.party_type_name = party_type_names.get(filer_type, filer.party_type_name)
            filer.save(update_fields=["party_type", "party_type_name", "updated_at"])
            set_filing_parties(draft, [filer])
            if draft.notice_email:
                # A party in their own case is reached at their own address,
                # and the review screen should stop naming one that no longer
                # applies to anything.
                draft.notice_email = ""
                draft.save(update_fields=["notice_email", "updated_at"])
            return _continue_from_parties(request, jurisdiction, draft, party_types, return_to)
        else:
            messages.error(request, "Choose your role in this case, or tell us you are filing for someone else.")

    roster = [
        {"party": party, "complete": party_is_complete(party, party_types=party_types)}
        for party in FilingParty.objects.filter(draft=draft)
    ]
    saved_filing_for = {
        party.pk for party in FilingParty.objects.filter(draft=draft, role="other", is_filing_party=True)
    }
    # The document naming the filer is a better answer than the case posture,
    # and a more concrete question to put to them: it can say which party they
    # are rather than which side they are probably on. Only asked while the
    # role question is still unanswered -- a filer who has said they are
    # filing for someone else has answered it, and does not need telling again
    # every time they come back to this screen.
    named_in_document = None if saved_filing_for else filer_name_match(draft)
    guessed_party_type = (
        None if filer.party_type or named_in_document is not None else guess_filer_party_type(draft, party_types)
    )
    # Which branch of the role question the screen comes back on. A filer who
    # has never answered gets neither pre-selected -- their own role is not
    # something to guess at on their behalf -- but an answer that has just
    # been refused is still their answer, and stays on the screen with the
    # error rather than making them find it again.
    attempted = request.POST.get("filer_party_type", "").strip() if request.method == "POST" else ""
    attempted_filing_for = {int(value) for value in request.POST.getlist("filing_for") if str(value).isdigit()}
    filing_for = attempted_filing_for or saved_filing_for
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "filer": filer,
        "return_to": request.GET.get("return_to", ""),
        "party_types": party_types,
        "roster": roster,
        "guessed_party_type": guessed_party_type,
        "not_a_party_value": NOT_A_PARTY,
        "named_in_document": named_in_document,
        "named_in_document_name": party_display_name(named_in_document) if named_in_document else "",
        "named_in_document_role": (
            (named_in_document.party_type_name or PARTY_SIDE_LABELS.get(named_in_document.party_side, ""))
            if named_in_document
            else ""
        ),
        "filing_for_someone_else": attempted == NOT_A_PARTY or (bool(saved_filing_for) and not filer.party_type),
        "filing_for_candidates": [
            {"party": party, "selected": party.pk in filing_for} for party in filing_party_candidates(draft)
        ],
        # Offered filled in with the filer's own address, because that is the
        # right answer most of the time and a blank box is a question nobody
        # asked to be asked. It stays editable for the times it is not.
        "notice_email": (
            request.POST.get("notice_email", "").strip() if request.method == "POST" else draft.notice_email
        )
        or filer.email,
    }
    context.update(get_workflow_context(WorkflowStepKey.PARTIES, jurisdiction, draft))
    return render(request, "efile/parties.html", context)
