from django.shortcuts import render

from efile.api.suffolk_api_views import get_tyler_token

from ..workflow import WorkflowStepKey, get_workflow_context


def filing_confirmation(request, jurisdiction):
    """Confirmation page after successful filing submission."""

    # You can add logic here to retrieve filing details from session
    # or from database if you're storing submitted filings
    is_logged_in = request.user.is_authenticated
    if not get_tyler_token(request, jurisdiction):
        is_logged_in = False

    context = {
        "is_logged_in": is_logged_in,
        "page_title": "Filing Confirmation",
        "success_message": "Your filing has been successfully submitted!",
    }
    context.update(get_workflow_context(WorkflowStepKey.CONFIRMATION, jurisdiction))

    return render(request, "efile/confirmation.html", context)
