"""The court selector's one endpoint: answers in, the next question out.

The screen holds no court data of its own. Every time the filer answers
something it posts the answers back here and redraws from what comes back, so
the questions, the courts they narrow to, and the court finally chosen are all
decided in one place against the live court list.
"""

import json
import logging

import requests
from django.views.decorators.http import require_http_methods

from efile.services.court_selection import (
    build_selection,
    derive_answers,
    derive_answers_from_guess,
    fetch_courts,
)
from efile.utils.jurisdiction_stuff import get_jurisdiction_from_request

from .base import APIResponseMixin

logger = logging.getLogger(__name__)

# Enough for the deepest configured cascade several times over, and small enough
# that a malformed query cannot turn into work.
MAX_ANSWERS = 20


def _answers(request):
    raw = request.GET.get("answers", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in list(parsed.items())[:MAX_ANSWERS] if value not in (None, "")}


@require_http_methods(["GET"])
def get_court_selector(request):
    """The questions to ask now, the courts they lead to, and the court chosen.

    ``available: false`` means this jurisdiction has no configured selector, and
    the caller should fall back to the flat court list it used before.
    """

    jurisdiction = get_jurisdiction_from_request(request)
    if not jurisdiction:
        return APIResponseMixin.error_response("Missing required jurisdiction parameter")

    answers = _answers(request)
    saved_court = request.GET.get("court", "")
    guessed_court = request.GET.get("guessed_court", "")
    from_document: list[str] = []

    try:
        courts = fetch_courts(jurisdiction)
    except (requests.RequestException, ValueError) as error:
        logger.warning("Could not load the court list for %s: %s", jurisdiction, error)
        return APIResponseMixin.error_response("We could not load the list of courts. Try again in a moment.")

    if not answers:
        # A saved court is only worth working backwards from while it is still a
        # court this service offers. One that is not -- a court retired since the
        # draft was saved, or a county heading that turned out to take no filings
        # -- would otherwise wipe out everything the document said, and leave the
        # filer starting from nothing.
        known = saved_court and any(court["value"] == saved_court for court in courts)
        if known:
            answers = derive_answers(jurisdiction, saved_court, courts)
            answers["court"] = saved_court
        elif guessed_court:
            # The document named a court. Whatever its words actually settle is
            # filled in and labelled as coming from the document; the rest stays
            # for the filer to answer.
            answers = derive_answers_from_guess(jurisdiction, guessed_court, courts)
            from_document = [key for key in answers if key != "court"]

    selection = build_selection(jurisdiction, answers, courts)
    if selection is None:
        return APIResponseMixin.success_response({"available": False})

    for step in selection["steps"]:
        step["from_document"] = step["id"] in from_document and bool(step["answer"])
    return APIResponseMixin.success_response({"available": True, **selection})
