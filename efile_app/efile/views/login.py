import logging

from django.contrib import messages
from django.shortcuts import redirect, render

from ..forms import EFileLoginForm

logger = logging.getLogger(__name__)


def efile_login(request):
    login_form = EFileLoginForm()
    if request.method == "POST":
        if "login_submit" in request.POST:
            login_form = EFileLoginForm(request.POST)
            if login_form.is_valid():
                import requests
                from django.conf import settings

                email = login_form.cleaned_data["email"]
                password = login_form.cleaned_data["password"]
                api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)
                try:
                    url = "https://efile-test.suffolklitlab.org/authenticate"
                    payload = {
                        "api_key": api_key,
                        "tyler-illinois": {
                            "username": email,
                            "password": password,
                        },
                    }

                    response = requests.post(url, json=payload, timeout=10)

                    logger.debug(response.text, response.status_code)

                    if response.status_code == 200:
                        data = response.json()
                        if data.get("tokens"):
                            # Save tokens in session
                            request.session["auth_tokens"] = data["tokens"]
                            # Save user email for use in forms
                            request.session["user_email"] = email
                            logger.info("User authenticated and session tokens stored")
                            messages.success(request, "Successfully logged in!")
                            return redirect("/options/")
                        else:
                            messages.error(request, data.get("message", "Invalid email or password."))
                    else:
                        messages.error(request, "Login service error. Please try again later.")
                except Exception as e:
                    logger.exception("Login request failed")
                    messages.error(request, f"Login failed: {str(e)}")
    context = {
        "login_form": login_form,
    }
    return render(request, "efile/login.html", context)


def efile_logout(request):
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
