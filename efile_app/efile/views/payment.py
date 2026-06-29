import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from efile.api.suffolk_api_views import get_tyler_token

from ..utils.case_data_utils import get_case_data
from ..workflow import get_workflow_context

logger = logging.getLogger(__name__)


def efile_payment(request, jurisdiction):
    """Review view for case details before final submission."""
    # Get case data from session
    case_data = get_case_data(request)
    logger.debug("Review view case_data %s", case_data)

    # Add user email from session if available and not already in case_data
    user_email = request.session.get("user_email")
    if user_email and not case_data.get("email"):
        case_data["email"] = user_email

    # If no case data exists, redirect back to expert form
    if not case_data:
        messages.error(request, "Please complete the case details first.")
        return redirect("expert_form", jurisdiction=jurisdiction)

    new_toga_url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/payments/new-toga-account"

    is_logged_in = request.user.is_authenticated
    if not get_tyler_token(request, jurisdiction):
        is_logged_in = False
    context = {
        "is_logged_in": is_logged_in,
        "new_toga_url": new_toga_url,
        "case_data": case_data,
    }
    context.update(get_workflow_context("payment", jurisdiction))

    return render(request, "efile/payment.html", context)
