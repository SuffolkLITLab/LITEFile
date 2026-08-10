from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingParty
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.people import get_case_questions, get_party_types, incomplete_parties
from efile.workflow import WorkflowStepKey, get_step_url, get_workflow_context


@require_http_methods(["GET", "POST"])
def party_details(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.PARTY_DETAILS,
        workflow_version=2,
    )
    party = get_object_or_404(FilingParty, draft=draft, role="other", pk=request.GET.get("party"))
    party_types = get_party_types(draft)
    party_type_names = {item["code"]: item["name"] for item in party_types}

    if request.method == "POST":
        party_kind = request.POST.get("party_kind", "person")
        party_type = request.POST.get("party_type", "").strip()
        if party_type and party_type not in party_type_names:
            party_type = ""
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        organization_name = request.POST.get("organization_name", "").strip()
        required_address = {
            "address_line_1": request.POST.get("address_line_1", "").strip(),
            "city": request.POST.get("city", "").strip(),
            "state": request.POST.get("state", "").strip(),
            "zip_code": request.POST.get("zip_code", "").strip(),
        }
        has_name = organization_name if party_kind == "organization" else first_name and last_name
        if not party_type or not has_name or not all(required_address.values()):
            messages.error(request, "Complete the party role, name, and mailing address.")
        else:
            party.party_type = party_type
            party.party_type_name = party_type_names.get(party_type, party.party_type_name)
            party.organization_name = organization_name if party_kind == "organization" else ""
            party.first_name = first_name if party_kind == "person" else ""
            party.middle_name = request.POST.get("middle_name", "").strip() if party_kind == "person" else ""
            party.last_name = last_name if party_kind == "person" else ""
            party.suffix = request.POST.get("suffix", "").strip() if party_kind == "person" else ""
            for field, value in required_address.items():
                setattr(party, field, value)
            party.address_line_2 = request.POST.get("address_line_2", "").strip()
            party.email = request.POST.get("email", "").strip()
            party.phone = request.POST.get("phone", "").strip()
            party.save()

            remaining = [item for item in incomplete_parties(draft) if item.pk != party.pk]
            if remaining:
                url = reverse("party_details", kwargs={"jurisdiction": jurisdiction})
                return redirect(f"{url}?party={remaining[0].pk}")

            has_questions = bool(get_case_questions(draft))
            draft.supplemental_fields = {
                **(draft.supplemental_fields or {}),
                "_case_questions_required": has_questions,
            }
            draft.current_step = WorkflowStepKey.CASE_QUESTIONS if has_questions else WorkflowStepKey.PAYMENT
            draft.save(update_fields=["supplemental_fields", "current_step", "updated_at"])
            return redirect(get_step_url(draft.current_step, jurisdiction))

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "party": party,
        "party_types": party_types,
        "party_kind": "organization" if party.organization_name else "person",
    }
    context.update(get_workflow_context(WorkflowStepKey.PARTY_DETAILS, jurisdiction, draft))
    return render(request, "efile/party_details.html", context)
