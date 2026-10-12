"""My cases: the court's record of what this account has filed.

The list is the court's, not ours -- we hold nothing here except which cases the
filer has archived. Archiving matters because the list only grows: an attorney
with three hundred filings should be able to say "not this one, not any more"
without losing the ability to go back and look.
"""

import logging

import requests
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDraft
from efile.services.filing_timing import court_filing_timing
from efile.services.filings import (
    DOCUMENT_LINK_DAYS,
    archive_case,
    cases_for_user,
    court_contact,
    court_names,
    describe_filing_detail,
    fetch_filing_detail,
    unarchive_case,
)
from efile.services.handoff import local_submission
from efile.utils.jurisdiction_stuff import has_jurisdiction_login, redirect_to_jurisdiction_login

logger = logging.getLogger(__name__)

SHOW_ARCHIVED_PARAM = "archived"


@require_http_methods(["GET", "POST"])
def filing_statuses(request, jurisdiction):
    """List the filer's court cases, newest activity first."""

    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    showing_archived = request.GET.get(SHOW_ARCHIVED_PARAM) == "1"

    if request.method == "POST":
        showing_archived = request.POST.get(SHOW_ARCHIVED_PARAM) == "1"
        action = request.POST.get("action")
        case_tracking_id = (request.POST.get("case_tracking_id") or "").strip()
        docket_number = request.POST.get("docket_number") or ""
        case_name = docket_number or request.POST.get("case_title") or "This case"
        if not case_tracking_id:
            messages.error(request, "We could not tell which case you meant.")
        elif action == "archive":
            archive_case(
                request.user,
                jurisdiction,
                case_tracking_id,
                docket_number=docket_number,
                case_title=request.POST.get("case_title") or "",
            )
            messages.success(request, f"{case_name} is archived. It is still here under archived cases.")
        elif action == "unarchive":
            unarchive_case(request.user, jurisdiction, case_tracking_id)
            messages.success(request, f"{case_name} is back in your list of cases.")
        else:
            messages.error(request, "We did not recognize that action.")
        destination = reverse("filing_statuses", kwargs={"jurisdiction": jurisdiction})
        if showing_archived:
            destination = f"{destination}?{SHOW_ARCHIVED_PARAM}=1"
        return redirect(destination)

    cases = []
    lookup_failed = False
    try:
        cases = cases_for_user(request, jurisdiction)
    except (requests.RequestException, TypeError, ValueError, KeyError, AttributeError):
        logger.exception("Could not load filing history for jurisdiction %s", jurisdiction)
        lookup_failed = True

    active = [case for case in cases if not case["is_archived"]]
    archived = [case for case in cases if case["is_archived"]]

    return render(
        request,
        "efile/view_statuses.html",
        {
            "is_logged_in": True,
            "cases": archived if showing_archived else active,
            "showing_archived": showing_archived,
            "active_count": len(active),
            "archived_count": len(archived),
            "lookup_failed": lookup_failed,
        },
    )


def filing_detail(request, jurisdiction, court_code, filing_id):
    """Everything the court will tell us about one filing.

    This is where a rejection comment and the filed documents themselves live.
    The documents are Tyler's own links, so they are handed to the filer as
    links rather than copied through this server.
    """

    if not has_jurisdiction_login(request, jurisdiction):
        return redirect_to_jurisdiction_login(request, jurisdiction)

    # A saved local submission must never be exposed through a guessed detail
    # URL belonging to another account. Older remote-only filings continue to
    # use the upstream token-scoped record. Another local user signed in to the
    # same Tyler account (re-created, say) is the same filer, not another account.
    local_draft = local_submission(request.user, jurisdiction, court_code, filing_id)
    if local_draft is None:
        others = FilingDraft.objects.filter(
            jurisdiction=jurisdiction, court_code=court_code, filing_identifiers__filing_id=str(filing_id)
        ).exclude(user=request.user)
        if request.user.tyler_user_id:
            others = others.exclude(user__tyler_user_id=request.user.tyler_user_id)
        if request.user.tyler_username:
            others = others.exclude(
                user__tyler_jurisdiction__iexact=request.user.tyler_jurisdiction,
                user__tyler_username__iexact=request.user.tyler_username,
            )
        if others.exists():
            raise Http404

    detail = None
    try:
        detail = describe_filing_detail(
            fetch_filing_detail(request, jurisdiction, court_code, filing_id),
            court_names(jurisdiction),
            timing=court_filing_timing(jurisdiction, court_code),
        )
    except (requests.RequestException, TypeError, ValueError, KeyError, AttributeError):
        logger.exception("Could not load filing detail for %s in %s", filing_id, jurisdiction)

    return render(
        request,
        "efile/filing_detail.html",
        {
            "is_logged_in": True,
            "filing": detail,
            "local_draft": local_draft,
            "court_code": court_code,
            "filing_id": filing_id,
            "court_contact": court_contact(jurisdiction, court_code),
            "document_link_days": DOCUMENT_LINK_DAYS,
        },
    )
