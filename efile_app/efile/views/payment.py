from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from requests import RequestException

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDocument, FilingParty
from efile.services.appeals import appeal_answers_complete
from efile.services.current_drafts import ensure_current_draft
from efile.services.document_previews import preview_fingerprint
from efile.services.draft_urls import draft_url
from efile.services.drafts import draft_snapshot, read_case_data
from efile.services.fee_estimates import estimate_fees
from efile.services.fee_quotes import fee_inputs_token
from efile.services.payment_accounts import payment_accounts
from efile.services.people import filing_parties
from efile.services.waiver_documents import has_waiver_document
from efile.utils.config_loader import config_loader
from efile.views.waiver_documents import is_removable_waiver

from ..workflow import (
    WorkflowStepKey,
    continue_step,
    continue_url,
    get_step_url,
    get_workflow_context,
    return_target,
    with_return_to,
)


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
    return_to = return_target(request)
    if not draft.court_code or not draft.case_type_code:
        messages.error(request, "Confirm the case information before choosing payment.")
        return redirect(with_return_to(get_step_url(WorkflowStepKey.EXTRACTION_REVIEW, jurisdiction), return_to))
    if not FilingDocument.objects.filter(draft=draft).exists():
        messages.error(request, "Add and organize at least one document before choosing payment.")
        return redirect(with_return_to(get_step_url(WorkflowStepKey.UPLOAD_DOCUMENTS, jurisdiction), return_to))
    filer = FilingParty.objects.filter(draft=draft, role="filer").first()
    # What has to be settled is who the filing is *for*, not whether the filer
    # is a party: someone filing for their child has no party type of their own
    # and is no less finished with this step.
    if filer is None or not filing_parties(draft):
        messages.error(request, "Complete the people in this filing before choosing payment.")
        return redirect(with_return_to(get_step_url(WorkflowStepKey.PARTIES, jurisdiction), return_to))

    if not appeal_answers_complete(draft):
        messages.error(request, "Complete the lower court information before checking fees.")
        return redirect(with_return_to(get_step_url(WorkflowStepKey.CASE_QUESTIONS, jurisdiction), return_to))

    documents = list(FilingDocument.objects.filter(draft=draft).order_by("role", "sort_order", "pk"))
    unchecked = [document for document in documents if document.preparation_reviewed_at is None]
    if request.method == "POST" and unchecked:
        # The page keeps Continue off until these are confirmed; this covers
        # a stale tab, so Review never sends the filer to another screen.
        messages.error(request, "Check your documents before you continue.")
        return redirect(with_return_to(get_step_url(WorkflowStepKey.PAYMENT, jurisdiction), return_to))

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
            draft.current_step = continue_step(draft, return_to, WorkflowStepKey.REVIEW)
            draft.save(
                update_fields=[
                    "selected_payment_account_id",
                    "selected_payment_account_name",
                    "selected_payment_account_type",
                    "current_step",
                    "updated_at",
                ]
            )
            return redirect(continue_url(draft, jurisdiction, return_to, WorkflowStepKey.REVIEW))

    context = {
        "documents": [document for document in documents if document.preparation_reviewed_at is not None],
        "document_checks": [
            {
                "document": document,
                "fingerprint": preview_fingerprint([document]),
                "removable": is_removable_waiver(document),
            }
            for document in unchecked
        ],
        "waiver_upload_url": draft_url(reverse("waiver_documents", kwargs={"jurisdiction": jurisdiction}), draft.pk),
        "has_waiver_document": has_waiver_document(draft),
        "is_logged_in": True,
        "return_to": return_to,
        "new_toga_url": f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/payments/new-toga-account",
        "case_data": read_case_data(draft),
        "filing_draft": draft_snapshot(draft),
        "selected_payment_account_id": draft.selected_payment_account_id,
        # Sent back with the fee request, so the quote is only kept if it
        # priced the filing as this page shows it (see fee_inputs_token).
        "fee_inputs_token": fee_inputs_token(draft),
        "fee_estimate": estimate_fees(draft),
        "fee_waiver": config_loader.load_jurisdiction_config(jurisdiction).get("fee_waiver", {}),
    }
    context.update(get_workflow_context(WorkflowStepKey.PAYMENT, jurisdiction, draft))
    return render(request, "efile/payment.html", context)
