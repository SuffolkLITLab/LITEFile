from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingParty
from efile.services.account_profile import cached_account_profile, default_state_code
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.workflow import RETURN_TO_REVIEW, WorkflowStepKey, get_return_url, get_workflow_context

# Account profile field -> the filer field it fills in when that field is blank.
_ACCOUNT_FIELDS = {
    "first_name": "first_name",
    "last_name": "last_name",
    "address_line_1": "address",
    "address_line_2": "address_line2",
    "city": "city",
    "state": "state",
    "zip_code": "zip",
    "phone": "phone",
}


def _prefill_from_account(filer, profile, user):
    """Fill blank filer fields from the account profile, in memory only.

    Nothing is saved: these are defaults the filer is being asked to confirm,
    and they become real data when they submit the form. Returns whether the
    profile was usable, which the page uses to skip its own fetch.
    """
    for field, profile_key in _ACCOUNT_FIELDS.items():
        if not getattr(filer, field, ""):
            setattr(filer, field, profile.get(profile_key) or "")
    # The account's own email never comes back from the court's firm record --
    # it is the address the filer signed in with.
    if not filer.email:
        filer.email = getattr(user, "email", "") or ""
    return True


@require_http_methods(["GET", "POST"])
def your_information(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.YOUR_INFORMATION,
        workflow_version=2,
    )
    filer, _created = FilingParty.objects.get_or_create(draft=draft, role="filer", sort_order=0)

    if request.method == "POST":
        required = {
            "first_name": "First name",
            "last_name": "Last name",
            "address_line_1": "Street address",
            "city": "City",
            "state": "State",
            "zip_code": "ZIP code",
            "email": "Email",
        }
        values = {field: request.POST.get(field, "").strip() for field in required}
        missing = [label for field, label in required.items() if not values[field]]
        if missing:
            messages.error(request, f"Complete these fields: {', '.join(missing)}.")
        else:
            for field, value in values.items():
                setattr(filer, field, value)
            filer.middle_name = request.POST.get("middle_name", "").strip()
            filer.suffix = request.POST.get("suffix", "").strip()
            filer.address_line_2 = request.POST.get("address_line_2", "").strip()
            filer.phone = request.POST.get("phone", "").strip()
            filer.save()
            next_step = (
                WorkflowStepKey.REVIEW if request.POST.get("return_to") == RETURN_TO_REVIEW else WorkflowStepKey.PARTIES
            )
            draft.current_step = next_step
            draft.save(update_fields=["current_step", "updated_at"])
            return redirect(get_return_url(request, jurisdiction, WorkflowStepKey.PARTIES))

    # Fill the blanks from the filer's e-filing account before rendering, not
    # afterwards from JavaScript: the filer should not watch their own name
    # appear a second or two after the form does. Anything already saved on the
    # draft wins, so a filer who corrected an address keeps the correction.
    profile = cached_account_profile(request, jurisdiction)
    prefilled = _prefill_from_account(filer, profile, request.user) if profile else False

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "filer": filer,
        "return_to": request.GET.get("return_to", ""),
        "court_code": draft.court_code,
        "default_state_code": default_state_code(jurisdiction),
        # Tells the page it does not need to fetch the profile again.
        "profile_prefilled": prefilled,
    }
    context.update(get_workflow_context(WorkflowStepKey.YOUR_INFORMATION, jurisdiction, draft))
    return render(request, "efile/your_information.html", context)
