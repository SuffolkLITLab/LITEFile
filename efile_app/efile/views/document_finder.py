"""Find the documents for what you want to file, before you have any.

Public pages: a filer can use them before signing in, or in the middle of a
filing from the Upload step and then go back to it. Nothing here changes a
draft. Starting a filing goes through the ordinary start-filing view, which
only learns whether this filing starts a case or joins one.
"""

from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from efile.services.document_finder import (
    FILING_PATH_LABELS,
    has_document_finder,
    help_resource,
    intent_detail,
    search_intents,
)
from efile.utils.config_loader import config_loader
from efile.utils.jurisdiction_stuff import has_jurisdiction_login

QUERY_LIMIT = 160


def _return_context(request, jurisdiction):
    """Where "back to my filing" goes, when the filer came from one.

    Only the Upload step links here, so only it can be returned to. The draft
    ID travels as ``filing`` rather than ``draft``: a ``draft`` parameter makes
    every page select that draft, and these pages are about no draft at all. It
    is passed through as a number and checked against the signed-in filer by
    the Upload view itself, like any other link to a draft.
    """

    if request.GET.get("from") != "upload":
        return {"return_query": "", "return_url": "", "return_draft": ""}
    url = reverse("upload_documents", kwargs={"jurisdiction": jurisdiction})
    query = "from=upload"
    draft = request.GET.get("filing", "")
    if not (draft.isascii() and draft.isdigit()):
        draft = ""
    if draft:
        url += f"?draft={draft}"
        query += f"&filing={draft}"
    return {"return_query": query, "return_url": url, "return_draft": draft}


def _base_context(request, jurisdiction):
    return {
        "page_jurisdiction": jurisdiction,
        "is_logged_in": has_jurisdiction_login(request, jurisdiction),
        "state_name": (config_loader.get_short_jurisdiction_config(jurisdiction) or {}).get("display_name", ""),
        "help": help_resource(jurisdiction),
        **_return_context(request, jurisdiction),
    }


def find_documents(request, jurisdiction):
    if jurisdiction not in config_loader.get_available_jurisdictions():
        return redirect("efile_choose_jurisdiction")

    query = request.GET.get("q", "").strip()[:QUERY_LIMIT]
    filing_path = request.GET.get("path", "")
    if filing_path not in FILING_PATH_LABELS:
        filing_path = ""
    found = search_intents(jurisdiction, query, filing_path)
    context = {
        **_base_context(request, jurisdiction),
        "available": has_document_finder(jurisdiction),
        "query": query,
        "filing_path": filing_path,
        "filing_paths": FILING_PATH_LABELS,
        "results": found["results"],
        "searched": found["searched"],
    }
    return render(request, "efile/find_documents.html", context)


def find_documents_intent(request, jurisdiction, intent_id):
    if jurisdiction not in config_loader.get_available_jurisdictions():
        return redirect("efile_choose_jurisdiction")

    intent = intent_detail(jurisdiction, intent_id)
    if intent is None:
        raise Http404("No such filing guide")
    context = {**_base_context(request, jurisdiction), "intent": intent}
    return render(request, "efile/find_documents_intent.html", context)
