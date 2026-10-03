"""Local-password/TOTP access, independent of court authentication."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django_otp.admin import OTPAdminAuthenticationForm
from django_otp.plugins.otp_totp.models import TOTPDevice

from efile.models import PrivacyRequest, StaffLoginThrottle
from efile.utils.config_loader import config_loader


def jurisdictions_for(user, role):
    if not user.is_active or not user.is_staff:
        return []
    if user.is_superuser:
        return config_loader.get_available_jurisdictions()
    return list(
        user.staff_roles.filter(role=role, jurisdiction__in=config_loader.get_available_jurisdictions()).values_list(
            "jurisdiction", flat=True
        )
    )


def require_scope(user, jurisdiction, role):
    if jurisdiction not in jurisdictions_for(user, role):
        raise PermissionDenied


class StaffLoginForm(OTPAdminAuthenticationForm):
    def clean(self):
        # Never call authenticate(): that can send a staff password to Tyler.
        username = self.cleaned_data.get("username", "")
        password = self.cleaned_data.get("password", "")
        key = salted_hmac("staff-login", username.casefold(), algorithm="sha256").hexdigest()
        now = timezone.now()
        error = None
        with transaction.atomic():
            throttle, _ = StaffLoginThrottle.objects.get_or_create(key=key, defaults={"window_started": now})
            throttle = StaffLoginThrottle.objects.select_for_update().get(pk=key)
            if throttle.window_started < now - timedelta(minutes=15):
                throttle.failures = 0
                throttle.window_started = now
            if throttle.failures >= 10:
                error = ValidationError("Sign-in temporarily locked. Try again in 15 minutes.")
            else:
                self.user_cache = ModelBackend().authenticate(self.request, username=username, password=password)
                try:
                    if self.user_cache is None:
                        raise self.get_invalid_login_error()
                    self.confirm_login_allowed(self.user_cache)
                    self.user_cache.backend = "django.contrib.auth.backends.ModelBackend"
                    self.clean_otp(self.user_cache)
                except ValidationError as exc:
                    error = exc
                    throttle.failures += 1
                else:
                    throttle.failures = 0
                    self.request.session["staff_verified_at"] = now.timestamp()
                    self.request.session.set_expiry(settings.LITEFILE_STAFF_SESSION_SECONDS)
            throttle.save()
        if error:
            raise error
        return self.cleaned_data

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser and not user.staff_roles.exists():
            raise self.get_invalid_login_error()

    def _chosen_device(self, user):
        device = super()._chosen_device(user)
        if device is not None and (not isinstance(device, TOTPDevice) or not device.confirmed):
            raise ValidationError("Choose a TOTP authenticator.")
        if device is None:
            # Only one supported factor type, even if other OTP apps are installed.
            device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
            if device is not None:
                device = TOTPDevice.objects.select_for_update().get(pk=device.pk)
        if device is None:
            raise ValidationError("A staff administrator must provision your TOTP authenticator before sign-in.")
        return device


class StaffIsolationMiddleware:
    """Keep staff identities out of filer workflows and frozen data unavailable."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(f"/{settings.LITEFILE_STAFF_PATH}/") and request.user.is_authenticated:
            if request.user.is_staff:
                return JsonResponse({"error": "Use a separate litigant account for filings."}, status=403)
            if (
                request.user.filing_drafts.filter(deletion_pending=True).exists()
                or PrivacyRequest.objects.filter(target=request.user, status="processing").exists()
            ):
                return JsonResponse({"error": "A verified data deletion is in progress."}, status=423)
        response = self.get_response(request)
        if request.path.startswith(f"/{settings.LITEFILE_STAFF_PATH}/"):
            response["Cache-Control"] = "no-store"
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
            # no-referrer makes native form POSTs send Origin: null, which
            # Django correctly rejects. Keep same-origin CSRF evidence while
            # suppressing referrers to every other origin.
            response["Referrer-Policy"] = "same-origin"
        return response
