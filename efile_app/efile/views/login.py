import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render

from efile.utils.config_loader import config_loader

from ..forms import EFileLoginForm

logger = logging.getLogger(__name__)


def efile_login(request, jurisdiction):
    if jurisdiction not in config_loader.get_available_jurisdictions():
        # TODO(brycew): better prediction of spell correction? (closest juris?)
        return redirect("efile_login", jurisdiction="illinois")

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
                        # data = response.json()
                        request.session["user_email"] = user.email
                        logger.info("User is auth: %s", user.is_authenticated)
                        logger.info("Session info: %s", request.session.keys())
                        logger.info("User authenticated and session tokens stored")
                        messages.success(request, "Successfully logged in!")
                        return redirect(f"/{jurisdiction}/options/")
                        # if data.get("tokens"):
                        # Save tokens in session
                        #    request.session["auth_tokens"] = data["tokens"]
                        # Save user email for use in forms
                        #    request.session["user_email"] = email
                    # else:
                    #     messages.error(request, data.get("message", "Invalid email or password."))
                    else:
                        messages.error(request, "Login service error. Please try again later.")
                except Exception as e:
                    logger.exception("Login request failed")
                    messages.error(request, f"Login failed: {str(e)}")
    context = {"login_form": login_form}
    return render(request, "efile/login.html", context)


def efile_logout(request, jurisdiction):
    """
    Custom logout view
    """
    from django.contrib.auth import logout
    from django.contrib.messages.api import get_messages

    # Clear any existing messages first
    storage = get_messages(request)
    for _message in storage:
        pass  # This consumes all messages

    logout(request)
    # Clear session data
    request.session.flush()
    messages.success(request, "You have been successfully logged out.")
    return redirect("efile_login")
