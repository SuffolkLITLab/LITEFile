import logging
import uuid

from django.shortcuts import redirect, render

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot

from ..utils.case_data_utils import (
    get_case_classification,
    get_name_sought_info,
    get_petitioner_info,
    get_upload_data,
)
from ..utils.django_helpers import flush_cache_stay_logged_in
from ..workflow import WorkflowStepKey, get_workflow_context

logger = logging.getLogger(__name__)


def efile_upload_first(request, jurisdiction):
    """Upload view for document submission and filing creation."""

    # Check if user is authenticated first
    if not request.user.is_authenticated:
        return redirect("efile_login", jurisdiction=jurisdiction)

    if not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    # Check if we need to clear cache (only when explicitly coming from options page button)
    clear_session = request.GET.get("clear_session", "false").lower() == "true"
    from_options = request.GET.get("from_options", "false").lower() == "true"

    logger.debug(f"Cache clear conditions - clear_session: {clear_session}, from_options: {from_options}")

    if clear_session and from_options:
        flush_cache_stay_logged_in(request.session)

        # They are actively starting a new session, so make the base info for that.
        request.session["session_id"] = str(uuid.uuid4())
        request.session["jurisdiction"] = jurisdiction
        request.session.modified = True

    filing_draft = ensure_current_draft(request, jurisdiction, current_step=WorkflowStepKey.UPLOAD_FIRST)

    # Could visit here from a back button press, so use upload data if any
    upload_data = get_upload_data(request, jurisdiction)

    # Get organized case information
    petitioner_info = get_petitioner_info(request, jurisdiction)
    name_sought_info = get_name_sought_info(request, jurisdiction)
    case_classification = get_case_classification(request, jurisdiction)

    context = {
        "is_logged_in": True,
        "upload_data": upload_data,
        "filing_draft": draft_snapshot(filing_draft),
        "petitioner_info": petitioner_info,
        "name_sought_info": name_sought_info,
        "case_classification": case_classification,
    }
    context.update(get_workflow_context(WorkflowStepKey.UPLOAD_FIRST, jurisdiction, filing_draft))

    return render(request, "efile/upload_first.html", context)
