import logging

import requests
from django.contrib import messages
from django.shortcuts import redirect, render

from ..forms import EFileRegistrationForm

logger = logging.getLogger(__name__)


def efile_register(request):
    STATE_NAMES = {
        "AL": "Alabama",
        "AK": "Alaska",
        "AZ": "Arizona",
        "AR": "Arkansas",
        "CA": "California",
        "CO": "Colorado",
        "CT": "Connecticut",
        "DE": "Delaware",
        "FL": "Florida",
        "GA": "Georgia",
        "HI": "Hawaii",
        "ID": "Idaho",
        "IL": "Illinois",
        "IN": "Indiana",
        "IA": "Iowa",
        "KS": "Kansas",
        "KY": "Kentucky",
        "LA": "Louisiana",
        "ME": "Maine",
        "MD": "Maryland",
        "MA": "Massachusetts",
        "MI": "Michigan",
        "MN": "Minnesota",
        "MS": "Mississippi",
        "MO": "Missouri",
        "MT": "Montana",
        "NE": "Nebraska",
        "NV": "Nevada",
        "NH": "New Hampshire",
        "NJ": "New Jersey",
        "NM": "New Mexico",
        "NY": "New York",
        "NC": "North Carolina",
        "ND": "North Dakota",
        "OH": "Ohio",
        "OK": "Oklahoma",
        "OR": "Oregon",
        "PA": "Pennsylvania",
        "RI": "Rhode Island",
        "SC": "South Carolina",
        "SD": "South Dakota",
        "TN": "Tennessee",
        "TX": "Texas",
        "UT": "Utah",
        "VT": "Vermont",
        "VA": "Virginia",
        "WA": "Washington",
        "WV": "West Virginia",
        "WI": "Wisconsin",
        "WY": "Wyoming",
    }
    if request.method == "POST":
        form = EFileRegistrationForm(request.POST)
        required_fields = [
            "first_name",
            "last_name",
            "street_address",
            "city",
            "zip_code",
            "state",
            "email",
            "phone",
            "password",
            "confirm_password",
        ]
        for field in required_fields:
            value = form.data.get(field, "").strip()
            logger.debug("Checking field presence: %s has_value=%s", field, bool(value))
            if not value:
                form.add_error(field, f"{field.replace('_', ' ').title()} is required.")

        import re

        email = form.data.get("email", "")
        email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+"
        if email and not re.match(email_regex, email):
            form.add_error("email", "Please enter a valid email address.")

        zip_code = form.data.get("zip_code", "")
        zip_regex = r"^\d{5}(-\d{4})?$"
        if zip_code and not re.match(zip_regex, zip_code):
            form.add_error("zip_code", "Please enter a valid ZIP code (e.g., 12345 or 12345-6789)")

        password = form.data.get("password", "")
        confirm_password = form.data.get("confirm_password", "")
        if password and confirm_password and password != confirm_password:
            form.add_error("confirm_password", "Passwords don't match.")

        def check_password_strength(pw):
            checks = [
                len(pw) >= 8,
                re.search(r"[a-z]", pw),
                re.search(r"[A-Z]", pw),
                re.search(r"[0-9]", pw),
                re.search(r"[^A-Za-z0-9]", pw),
            ]
            return sum(bool(c) for c in checks)

        if password and check_password_strength(password) < 3:
            form.add_error(
                "password",
                ("Password must be stronger (at least 3 of: 8+ chars, lowercase, uppercase, number, symbol)"),
            )

        if form.errors:
            return render(request, "efile/register.html", {"form": form})

        if form.is_valid():
            state_abbr = form.cleaned_data["state"]
            state_full = STATE_NAMES.get(state_abbr, state_abbr).lower()
            data = {
                "registrationType": "INDIVIDUAL",
                "firstName": form.cleaned_data["first_name"],
                "middleName": form.cleaned_data.get("middle_name", ""),
                "lastName": form.cleaned_data["last_name"],
                "streetAddressLine1": form.cleaned_data["street_address"],
                "streetAddressLine2": form.cleaned_data.get("street_address_2", ""),
                "city": form.cleaned_data["city"],
                "stateCode": state_abbr,
                "zipCode": form.cleaned_data["zip_code"],
                "countryCode": "US",
                "email": form.cleaned_data["email"],
                "phoneNumber": form.cleaned_data.get("phone", ""),
                "password": form.cleaned_data["password"],
            }
            try:
                from django.conf import settings

                api_key = getattr(settings, "SUFFOLK_EFILE_API_KEY", None)
                headers = {"x-api-key": api_key} if api_key else {}
                endpoint = f"https://efile-test.suffolklitlab.org/jurisdictions/{state_full}/adminusers/users"

                response = requests.post(endpoint, json=data, headers=headers, timeout=10)

                logger.debug(
                    "POST %s with header keys=%s payload keys=%s", endpoint, list(headers.keys()), list(data.keys())
                )
                logger.debug("Headers: %s", headers)
                logger.debug("Payload: %s", data)

                response = requests.post(endpoint, json=data, headers=headers, timeout=10)

                logger.debug(
                    "Registration response: status=%s content_type=%s",
                    response.status_code,
                    response.headers.get("Content-Type"),
                )
                logger.debug("Response body: %s", response.text)
                if response.status_code == 201:
                    content_type = response.headers.get("Content-Type", "")
                    tokens = response.json().get("tokens") if content_type.startswith("application/json") else None
                    if tokens:
                        request.session["user_tokens"] = tokens
                    messages.success(
                        request,
                        "Registration successful! Please log in with your new account after verifying your email.",
                    )
                    # Redirect to login page
                    return redirect("/login/")
                else:
                    try:
                        error_msg = response.json().get("error") or response.text
                    except Exception:
                        error_msg = response.text
                    messages.error(request, f"Registration failed: {error_msg}")
            except Exception as e:
                logger.exception("Registration request failed")
                messages.error(request, f"Registration failed: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Always show a blank form on reload
        form = EFileRegistrationForm()
    return render(request, "efile/register.html", {"form": form})
