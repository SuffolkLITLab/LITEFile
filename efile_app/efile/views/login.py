from django.contrib import messages
from django.shortcuts import redirect, render

from ..forms import EFileLoginForm


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
                    response = requests.post(
                        "https://efile-test.suffolklitlab.org/authenticate",
                        json={
                            "api_key": api_key,
                            "tyler-illinois": {
                                "username": email,
                                "password": password,
                            },
                        },
                        timeout=10,
                    )
                    print(response.text, response.status_code)
                    if response.status_code == 200:
                        print(response)
                        data = response.json()
                        print(data)
                        if data.get("tokens"):
                            # Save tokens in session
                            request.session['auth_tokens'] = data['tokens']

                            print(request)
                            messages.success(request, 'Successfully logged in!')
                            return redirect('/options/')
                        else:
                            messages.error(request, data.get("message", "Invalid email or password."))
                    else:
                        messages.error(request, "Login service error. Please try again later.")
                except Exception as e:
                    messages.error(request, f"Login failed: {str(e)}")
    context = {
        "login_form": login_form,
    }
    return render(request, "efile/login.html", context)
