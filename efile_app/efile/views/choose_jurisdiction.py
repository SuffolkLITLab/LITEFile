import logging

from django.shortcuts import render

from efile.utils.config_loader import config_loader

logger = logging.getLogger(__name__)


def choose_jurisdiction(request):
    jurisdictions = config_loader.get_available_jurisdictions()
    jurisdiction_details = [config_loader.load_jurisdiction_config(j) for j in jurisdictions]
    return render(request, "efile/choose_jurisdiction.html", {"jurisdiction_details": jurisdiction_details})
