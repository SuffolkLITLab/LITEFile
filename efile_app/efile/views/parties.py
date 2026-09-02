from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingParty
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.people import (
    NOT_A_PARTY,
    absorb_filer_duplicates,
    apply_party_sides,
    ensure_required_parties,
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
        if action == "remove":
            party = get_object_or_404(FilingParty, pk=request.POST.get("party_id"), draft=draft, role="other")
            party.delete()
            if request.POST.get("instead") == "me":
                # "Actually, this is me" on the add-a-person screen. The blank
                # row goes, because the filer is already on this draft once and
                # a second copy of them would reach the court as two people.
                messages.success(request, "Choose your own role below to add yourself as a party.")
                return redirect(f"{_parties_url(jurisdiction, return_to)}#your-role")
            messages.success(request, "Party removed.")
            return redirect(_parties_url(jurisdiction, return_to))

        filer_type = request.POST.get("filer_party_type", "").strip()
        if filer_type == NOT_A_PARTY:
            # Filing for someone else. Tyler still needs a party to file on
            # behalf of, so the filer names one instead of becoming one.
            chosen = _chosen_filing_parties(request, draft)
            if not chosen:
                messages.error(request, "Choose who you are filing for.")
            else:
                filer.party_type = ""
                filer.party_type_name = ""
                filer.save(update_fields=["party_type", "party_type_name", "updated_at"])
                set_filing_parties(draft, chosen)
                return _continue_from_parties(request, jurisdiction, draft, party_types, return_to)
        elif filer_type in party_type_names:
            filer.party_type = filer_type
            filer.party_type_name = party_type_names.get(filer_type, filer.party_type_name)
            filer.save(update_fields=["party_type", "party_type_name", "updated_at"])
            set_filing_parties(draft, [filer])
            return _continue_from_parties(request, jurisdiction, draft, party_types, return_to)
        else:
            messages.error(request, "Choose your role in this case, or tell us you are filing for someone else.")

    roster = [
        {"party": party, "complete": party_is_complete(party, party_types=party_types)}
        for party in FilingParty.objects.filter(draft=draft)
    ]
    guessed_party_type = None if filer.party_type else guess_filer_party_type(draft, party_types)
    # Which branch of the role question the screen comes back on. A filer who
    # has never answered gets neither pre-selected -- their own role is not
    # something to guess at on their behalf -- but an answer that has just
    # been refused is still their answer, and stays on the screen with the
    # error rather than making them find it again.
    saved_filing_for = {
        party.pk for party in FilingParty.objects.filter(draft=draft, role="other", is_filing_party=True)
    }
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
        "filing_for_someone_else": attempted == NOT_A_PARTY or (bool(saved_filing_for) and not filer.party_type),
        "filing_for_candidates": [
            {"party": party, "selected": party.pk in filing_for} for party in filing_party_candidates(draft)
        ],
    }
    context.update(get_workflow_context(WorkflowStepKey.PARTIES, jurisdiction, draft))
    return render(request, "efile/parties.html", context)
