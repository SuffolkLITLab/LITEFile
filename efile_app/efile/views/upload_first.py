import logging

from django.shortcuts import redirect, render

from ..utils.case_data_utils import (
    get_case_classification,
    get_name_sought_info,
    get_petitioner_info,
    get_upload_data,
)
from ..utils.django_helpers import flush_cache_stay_logged_in

logger = logging.getLogger(__name__)


def efile_upload_first(request, jurisdiction):
    """Upload view for document submission and filing creation."""

    # Check if user is authenticated first
    if not request.user.is_authenticated:
        return redirect("efile_login", jurisdiction=jurisdiction)

    # Check if we need to clear cache (only when explicitly coming from options page button)
    clear_session = request.GET.get("clear_session", "false").lower() == "true"
    from_options = request.GET.get("from_options", "false").lower() == "true"

    logger.debug(f"Cache clear conditions - clear_session: {clear_session}, from_options: {from_options}")

    if clear_session and from_options:
        flush_cache_stay_logged_in(request.session)

    # Could visit here from a back button press, so use upload data if any
    upload_data = get_upload_data(request)

    # Get organized case information
    petitioner_info = get_petitioner_info(request)
    name_sought_info = get_name_sought_info(request)
    case_classification = get_case_classification(request)

    context = {
        "upload_data": upload_data,
        "petitioner_info": petitioner_info,
        "name_sought_info": name_sought_info,
        "case_classification": case_classification,
    }

    return render(request, "efile/upload_first.html", context)
