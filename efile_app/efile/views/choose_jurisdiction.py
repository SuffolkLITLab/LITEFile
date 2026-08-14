import logging

from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render

from efile.utils.config_loader import config_loader

logger = logging.getLogger(__name__)


def choose_jurisdiction(request: HttpRequest) -> HttpResponse:
    jurisdictions = config_loader.get_available_jurisdictions()
    jurisdiction_details = [config_loader.load_jurisdiction_config(j) for j in jurisdictions]
    return render(request, "efile/choose_jurisdiction.html", {"jurisdiction_details": jurisdiction_details})


def change_jurisdiction(request: HttpRequest, jurisdiction: str) -> HttpResponse:
    """Discard the active account/filing context before showing the state picker."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    logout(request)
    return redirect("efile_choose_jurisdiction")
