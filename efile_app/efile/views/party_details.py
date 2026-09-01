from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingParty
from efile.party_sides import PartySide, side_for_party_type_name
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.party_requirements import address_is_blank, party_address_requirement
from efile.services.people import (
    get_case_questions,
    get_party_types,
    incomplete_parties,
    needs_amount_in_controversy,
)
from efile.workflow import RETURN_TO_REVIEW, WorkflowStepKey, get_step_url, get_workflow_context, with_return_to


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
    show_optional_address = not address_is_blank(party)

    if request.method == "POST":
        party_kind = request.POST.get("party_kind", "person")
        party_type = request.POST.get("party_type", "").strip()
        if party_type and party_type not in party_type_names:
            party_type = ""
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        organization_name = request.POST.get("organization_name", "").strip()
        address = {
            "address_line_1": request.POST.get("address_line_1", "").strip(),
            "city": request.POST.get("city", "").strip(),
            "state": request.POST.get("state", "").strip(),
            "zip_code": request.POST.get("zip_code", "").strip(),
        }
        address_line_2 = request.POST.get("address_line_2", "").strip()
        selected_party = FilingParty(
            draft=draft,
            party_type=party_type,
            party_type_name=party_type_names.get(party_type, ""),
        )
        address_requirement = party_address_requirement(draft, selected_party, party_types=party_types)
        address_started = any(address.values()) or bool(address_line_2)
        address_complete = all(address.values())
        show_optional_address = address_started
        has_name = organization_name if party_kind == "organization" else first_name and last_name
        if not party_type or not has_name:
            messages.error(request, "Complete the party role and name.")
        elif (address_requirement.required or address_started) and not address_complete:
            # Keep the attempted address visible when returning validation
            # errors. These assignments only affect this rendered instance;
            # nothing is saved until every required part is present.
            for field, value in address.items():
                setattr(party, field, value)
            party.address_line_2 = address_line_2
            if address_requirement.required:
                messages.error(request, f"Complete the mailing address. {address_requirement.reason}")
            else:
                messages.error(request, "Complete the optional mailing address, or clear all of its fields.")
        else:
            party.party_type = party_type
            party.party_type_name = party_type_names.get(party_type, party.party_type_name)
            # A type chosen by hand is the better answer, so the side follows
            # it rather than the other way round. A type with no side in its
            # name ("Guardian Ad Litem") is exactly what "someone else" means.
            party.party_side = side_for_party_type_name(party.party_type_name) or PartySide.OTHER
            party.organization_name = organization_name if party_kind == "organization" else ""
            party.first_name = first_name if party_kind == "person" else ""
            party.middle_name = request.POST.get("middle_name", "").strip() if party_kind == "person" else ""
            party.last_name = last_name if party_kind == "person" else ""
            party.suffix = request.POST.get("suffix", "").strip() if party_kind == "person" else ""
            for field, value in address.items():
                setattr(party, field, value)
            party.address_line_2 = address_line_2
            party.email = request.POST.get("email", "").strip()
            party.phone = request.POST.get("phone", "").strip()
            party.save()

            return_to = request.POST.get("return_to")
            remaining = [item for item in incomplete_parties(draft, party_types=party_types) if item.pk != party.pk]
            if remaining:
                url = reverse("party_details", kwargs={"jurisdiction": jurisdiction})
                return redirect(with_return_to(f"{url}?party={remaining[0].pk}", return_to))

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

    address_requirement = party_address_requirement(draft, party, party_types=party_types)
    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "party": party,
        "party_types": party_types,
        "party_kind": "organization" if party.organization_name else "person",
        "return_to": request.GET.get("return_to", ""),
        "court_code": draft.court_code,
        "address_required": address_requirement.required,
        "address_reason": address_requirement.reason,
        "show_optional_address": show_optional_address,
    }
    context.update(get_workflow_context(WorkflowStepKey.PARTY_DETAILS, jurisdiction, draft))
    return render(request, "efile/party_details.html", context)
