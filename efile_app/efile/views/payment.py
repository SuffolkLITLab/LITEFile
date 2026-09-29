from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from requests import RequestException

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument, FilingParty
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot, read_case_data
from efile.services.fee_estimates import estimate_fees
from efile.services.fee_quotes import fee_inputs_token
from efile.services.payment_accounts import payment_accounts
from efile.services.people import filing_parties

from ..workflow import WorkflowStepKey, get_step_url, get_workflow_context


@require_http_methods(["GET", "POST"])
def efile_payment(request, jurisdiction):
    """Choose a payment account and quote court fees for the durable draft."""
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.PAYMENT,
        workflow_version=2,
    )
    if not draft.court_code or not draft.case_type_code:
        messages.error(request, "Confirm the case information before choosing payment.")
        return redirect("extraction_review", jurisdiction=jurisdiction)
    if not FilingDocument.objects.filter(draft=draft).exists():
        messages.error(request, "Add and organize at least one document before choosing payment.")
        return redirect("upload_documents", jurisdiction=jurisdiction)
    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    # What has to be settled is who the filing is *for*, not whether the filer
    # is a party: someone filing for their child has no party type of their own
    # and is no less finished with this step.
    if filer is None or not filing_parties(draft):
        messages.error(request, "Complete the people in this filing before choosing payment.")
        return redirect("parties", jurisdiction=jurisdiction)

    if request.method == "POST":
        account_id = request.POST.get("selected_payment_account", "").strip()
        try:
            accounts = payment_accounts(jurisdiction, get_tyler_token(request, jurisdiction)) if account_id else []
            account = next((a for a in accounts if str(a["paymentAccountID"]) == account_id), None)
        except (RequestException, ValueError):
            account = None
        if not account:
            messages.error(request, "Choose a payment method to continue.")
        else:
            draft.selected_payment_account_id = account_id
            draft.selected_payment_account_name = account.get("accountName") or "Selected payment method"
            draft.selected_payment_account_type = account.get("paymentAccountTypeCode", "")
            # The fee quote itself is not read from this form: the fee API
            # recorded it on the draft, with what it was priced on, when it
            # answered (see efile.services.fee_quotes).
            draft.current_step = WorkflowStepKey.REVIEW
            draft.save(
                update_fields=[
                    "selected_payment_account_id",
                    "selected_payment_account_name",
                    "selected_payment_account_type",
                    "current_step",
                    "updated_at",
                ]
            )
            return redirect(get_step_url(WorkflowStepKey.REVIEW, jurisdiction))

    context = {
        "is_logged_in": True,
        "new_toga_url": f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/payments/new-toga-account",
        "case_data": read_case_data(draft),
        "filing_draft": draft_snapshot(draft),
        "selected_payment_account_id": draft.selected_payment_account_id,
        # Sent back with the fee request, so the quote is only kept if it
        # priced the filing as this page shows it (see fee_inputs_token).
        "fee_inputs_token": fee_inputs_token(draft),
        "fee_estimate": estimate_fees(draft),
    }
    context.update(get_workflow_context(WorkflowStepKey.PAYMENT, jurisdiction, draft))
    return render(request, "efile/payment.html", context)
