import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot

from ..utils.case_data_utils import (
    get_case_classification,
    get_case_data,
    get_name_sought_info,
    get_petitioner_info,
    get_upload_data,
)
from ..workflow import WorkflowStepKey, get_workflow_context

logger = logging.getLogger(__name__)


def efile_upload(request, jurisdiction):
    """Upload view for document submission and filing creation."""

    if not request.user.is_authenticated:
        return redirect("efile_login", jurisdiction=jurisdiction)

    case_data = get_case_data(request)

    if not case_data:
        messages.error(request, gettext("Please complete the case details first."))
        return redirect("efile_options", jurisdiction=jurisdiction)

    filing_draft = ensure_current_draft(request, jurisdiction, current_step=WorkflowStepKey.DOCUMENTS)

    petitioner_info = get_petitioner_info(request)
    name_sought_info = get_name_sought_info(request)
    case_classification = get_case_classification(request)

    friendly_case_type = case_data.get("case_type_name", case_classification["case_type"])
    friendly_filing_type = case_data.get("filing_type_name", case_classification["filing_type"])
    friendly_court = case_data.get("court_name", case_classification["court"])

    upload_data = get_upload_data(request)

    is_logged_in = request.user.is_authenticated
    if not get_tyler_token(request, jurisdiction):
        is_logged_in = False
    context = {
        "is_logged_in": is_logged_in,
        "case_data": case_data,
        "upload_data": upload_data,
        "filing_draft": draft_snapshot(filing_draft),
        "petitioner_info": petitioner_info,
        "name_sought_info": name_sought_info,
        "case_classification": case_classification,
        "case_type_name": friendly_case_type,
        "filing_type": friendly_filing_type,
        "court": friendly_court,
        "case_type_raw": case_classification["case_type"],
        "category_type_raw": case_classification["case_category"],
        "filing_type_raw": case_classification["filing_type"],
        "court_raw": case_classification["court"],
    }
    context.update(get_workflow_context(WorkflowStepKey.DOCUMENTS, jurisdiction))

    return render(request, "efile/upload.html", context)
