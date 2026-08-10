from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingParty
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.people import ensure_required_parties, get_case_questions, get_party_types, incomplete_parties
from efile.workflow import WorkflowStepKey, get_step_url, get_workflow_context


def _party_details_url(jurisdiction, party):
    return f"{reverse('party_details', kwargs={'jurisdiction': jurisdiction})}?party={party.pk}"


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

    if request.method == "POST":
        action = request.POST.get("action", "continue")
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
            return redirect(_party_details_url(jurisdiction, party))
        if action == "remove":
            party = get_object_or_404(FilingParty, pk=request.POST.get("party_id"), draft=draft, role="other")
            party.delete()
            messages.success(request, "Party removed.")
            return redirect("parties", jurisdiction=jurisdiction)

        filer_type = request.POST.get("filer_party_type", "").strip()
        if not filer_type:
            messages.error(request, "Choose your role in this case.")
        else:
            filer.party_type = filer_type
            filer.party_type_name = party_type_names.get(filer_type, filer.party_type_name)
            filer.save(update_fields=["party_type", "party_type_name", "updated_at"])
            ensure_required_parties(draft, party_types)
            incomplete = incomplete_parties(draft)
            if incomplete:
                draft.current_step = WorkflowStepKey.PARTY_DETAILS
                draft.save(update_fields=["current_step", "updated_at"])
                return redirect(_party_details_url(jurisdiction, incomplete[0]))

            has_questions = bool(get_case_questions(draft))
            draft.supplemental_fields = {
                **(draft.supplemental_fields or {}),
                "_case_questions_required": has_questions,
            }
            draft.current_step = WorkflowStepKey.CASE_QUESTIONS if has_questions else WorkflowStepKey.PAYMENT
            draft.save(update_fields=["supplemental_fields", "current_step", "updated_at"])
            return redirect(get_step_url(draft.current_step, jurisdiction))

    roster = [
        {
            "party": party,
            "complete": bool(party.party_type and (party.organization_name or (party.first_name and party.last_name))),
        }
        for party in FilingParty.objects.filter(draft=draft)
    ]
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "filer": filer,
        "party_types": party_types,
        "roster": roster,
    }
    context.update(get_workflow_context(WorkflowStepKey.PARTIES, jurisdiction, draft))
    return render(request, "efile/parties.html", context)
