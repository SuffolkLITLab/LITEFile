from django.contrib import messages
from django.shortcuts import redirect, render

from ..forms import EFileRegistrationForm


def efile_register(request):
    if request.method == "POST":
        form = EFileRegistrationForm(request.POST)
        # Backend validation matching frontend JS
        errors = []
        required_fields = [
            "first_name",
            "last_name",
            "street_address",
            "city",
            "zip_code",
            "state",
            "county",
            "email",
            "password",
            "confirm_password",
        ]
        for field in required_fields:
            value = form.data.get(field, "").strip()
            if not value:
                errors.append(f"{field.replace('_', ' ').title()} is required.")

        # Email format
        import re

        email = form.data.get("email", "")
        email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
        if email and not re.match(email_regex, email):
            errors.append("Please enter a valid email address.")

        # Zip code format
        zip_code = form.data.get("zip_code", "")
        zip_regex = r"^\d{5}(-\d{4})?$"
        if zip_code and not re.match(zip_regex, zip_code):
            errors.append("Please enter a valid ZIP code (e.g., 12345 or 12345-6789)")

        # Password match
        password = form.data.get("password", "")
        confirm_password = form.data.get("confirm_password", "")
        if password and confirm_password and password != confirm_password:
            errors.append("Passwords don't match.")

        # Password strength
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
            errors.append(
                "Password must be stronger (at least 3 of: 8+ chars, lowercase, uppercase, number, symbol)"
            )

        if errors:
            for error in errors:
                messages.error(request, error)
            # Don't proceed to API call
            return render(request, "efile/register.html", {"form": form})

        if form.is_valid():
            data = {
                "registrationType": "INDIVIDUAL",
                "firstName": form.cleaned_data["first_name"],
                "middleName": form.cleaned_data.get("middle_name", ""),
                "lastName": form.cleaned_data["last_name"],
                "streetAddressLine1": form.cleaned_data["street_address"],
                "streetAddressLine2": form.cleaned_data.get("street_address_2", ""),
                "city": form.cleaned_data["city"],
                "state": form.cleaned_data["state"],
                "zipCode": form.cleaned_data["zip_code"],
                "countryCode": "US",
                "county": form.cleaned_data["county"],
                "email": form.cleaned_data["email"],
                "phoneNumber": form.cleaned_data.get("phone", ""),
                # "emailUpdates": form.cleaned_data.get("email_updates", False),
                # "textUpdates": form.cleaned_data.get("text_updates", False),
                "password": form.cleaned_data["password"],
            }
            try:
                import requests

                response = requests.post(
                    "https://efile-test.suffolklitlab.org/jurisdictions/illinois/adminusers/users",
                    json=data,
                    timeout=10,
                )
                if response.status_code == 201:
                    messages.success(
                        request, "Registration successful! Please log in with your new account."
                    )
                    return redirect("efile_login")
                else:
                    try:
                        error_msg = response.json().get("error") or response.text
                    except Exception:
                        error_msg = response.text
                    messages.error(request, f"Registration failed: {error_msg}")
            except Exception as e:
                messages.error(request, f"Registration failed: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = EFileRegistrationForm()
    return render(request, "efile/register.html", {"form": form})
