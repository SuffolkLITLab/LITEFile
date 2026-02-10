"""
Actual pages / paths for logging in and out.

Depend on the api.auth_views that implement the actual functionality.
"""

import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render

from efile.utils.config_loader import config_loader

from ..forms import EFileLoginForm

logger = logging.getLogger(__name__)


def efile_login(request, jurisdiction):
    if jurisdiction not in config_loader.get_available_jurisdictions():
        return redirect("efile_choose_jurisdiction")

    login_form = EFileLoginForm()
    if request.method == "POST":
        if "login_submit" in request.POST:
            login_form = EFileLoginForm(request.POST)
            if login_form.is_valid():
                email = login_form.cleaned_data["email"]
                password = login_form.cleaned_data["password"]
                try:
                    user = authenticate(request, username=email, password=password)

                    if user is not None:  # response.status_code == 200:
                        login(request, user)
                        request.session["user_email"] = user.email
                        messages.success(request, "Successfully logged in!")
                        return redirect(f"/jurisdiction/{jurisdiction}/options/")
                    else:
                        messages.error(request, "Login service error. Please try again later.")
                except Exception as e:
                    logger.exception("Login request failed")
                    messages.error(request, f"Login failed: {str(e)}")
    config = config_loader.load_jurisdiction_config(jurisdiction)
    context = {"login_form": login_form, "config": config}
    return render(request, "efile/login.html", context)


def efile_logout(request, jurisdiction):
    """
    Custom logout view
    """
    from efile.authentication import SuffolkEFileBackend

    SuffolkEFileBackend.logout(request)

    messages.success(request, "You have been successfully logged out.")
    return redirect("efile_login", jurisdiction=jurisdiction)
