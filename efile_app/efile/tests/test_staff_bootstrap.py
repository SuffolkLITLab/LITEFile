"""Initial staff credentials come from explicit secrets, never defaults."""

import base64
import io
import secrets

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

from efile.models import FilingDocument, FilingDraft, UsageCounter, UserProfile

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def bootstrap_environment(monkeypatch):
    for suffix in ("USERNAME", "PASSWORD", "EMAIL", "TOTP_SECRET"):
        monkeypatch.delenv(f"LITEFILE_STAFF_BOOTSTRAP_{suffix}", raising=False)


def configure(monkeypatch):
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv("LITEFILE_STAFF_BOOTSTRAP_USERNAME", "environment-admin")
    monkeypatch.setenv("LITEFILE_STAFF_BOOTSTRAP_PASSWORD", password)
    return password


def test_bootstrap_has_no_default_account():
    with pytest.raises(CommandError, match="no default account"):
        call_command("bootstrap_staff")
    assert not UserProfile.objects.exists()


@pytest.mark.parametrize("password", ["", "password"])
def test_bootstrap_rejects_missing_or_weak_password(monkeypatch, password):
    configure(monkeypatch)
    monkeypatch.setenv("LITEFILE_STAFF_BOOTSTRAP_PASSWORD", password)
    with pytest.raises(CommandError):
        call_command("bootstrap_staff")
    assert not UserProfile.objects.exists()
    assert not TOTPDevice.objects.exists()


def test_generated_totp_and_password_are_created_together(monkeypatch):
    password = configure(monkeypatch)
    output = io.StringIO()
    call_command("bootstrap_staff", stdout=output)
    user = UserProfile.objects.get(username="environment-admin")
    device = TOTPDevice.objects.get(user=user)
    assert user.is_active and user.is_staff and user.is_superuser
    assert user.check_password(password)
    assert device.confirmed and len(bytes.fromhex(device.key)) == 20
    assert device.config_url in output.getvalue()
    assert password not in output.getvalue()


def test_supplied_secret_and_repeated_bootstrap_never_echo_or_overwrite(monkeypatch):
    password = configure(monkeypatch)
    key = b"t" * 20
    secret = base64.b32encode(key).decode()
    monkeypatch.setenv("LITEFILE_STAFF_BOOTSTRAP_TOTP_SECRET", secret)
    output = io.StringIO()
    call_command("bootstrap_staff", stdout=output)
    device = TOTPDevice.objects.get()
    assert device.key == key.hex()
    assert secret not in output.getvalue()
    assert "otpauth://" not in output.getvalue()
    monkeypatch.setenv("LITEFILE_STAFF_BOOTSTRAP_PASSWORD", secrets.token_urlsafe(24))
    monkeypatch.setenv("LITEFILE_STAFF_BOOTSTRAP_TOTP_SECRET", base64.b32encode(b"x" * 20).decode())
    call_command("bootstrap_staff", stdout=output)
    device.refresh_from_db()
    assert device.key == key.hex()
    assert TOTPDevice.objects.count() == 1
    assert UserProfile.objects.get().check_password(password)


@pytest.mark.parametrize("secret", ["not-a-base32-secret!", "JBSWY3DPEHPK3PXP"])
def test_invalid_or_short_totp_rolls_back_all_creation(monkeypatch, secret):
    configure(monkeypatch)
    monkeypatch.setenv("LITEFILE_STAFF_BOOTSTRAP_TOTP_SECRET", secret)
    with pytest.raises(CommandError):
        call_command("bootstrap_staff")
    assert not UserProfile.objects.exists()


def test_bootstrap_never_promotes_existing_filer(monkeypatch):
    configure(monkeypatch)
    original_password = secrets.token_urlsafe(24)
    user = UserProfile.objects.create_user(username="environment-admin", password=original_password)
    with pytest.raises(CommandError, match="cannot promote"):
        call_command("bootstrap_staff")
    user.refresh_from_db()
    assert not user.is_staff and not user.is_superuser
    assert user.check_password(original_password)


def test_demo_is_local_idempotent_and_has_no_uploads(settings, monkeypatch):
    settings.DEBUG = True
    settings.LITEFILE_ANALYTICS_ENABLED = False
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    output = io.StringIO()
    call_command("seed_staff_demo", stdout=output)
    before = list(UsageCounter.objects.values_list("pk", "count", "contributors").order_by("pk"))
    assert before and all(contributors == 5 for _, _, contributors in before)
    draft_count = FilingDraft.objects.count()
    assert draft_count > 0
    assert not FilingDocument.objects.exists()
    assert all(user.analytics_excluded and not user.has_usable_password() for user in UserProfile.objects.all())
    call_command("seed_staff_demo", stdout=output)
    assert list(UsageCounter.objects.values_list("pk", "count", "contributors").order_by("pk")) == before
    assert FilingDraft.objects.count() == draft_count


@pytest.mark.parametrize("deployed", [False, True])
def test_demo_refuses_production_or_deployed_host(settings, monkeypatch, deployed):
    settings.DEBUG = deployed
    if deployed:
        monkeypatch.setenv("FLY_APP_NAME", "deployed-app")
    else:
        monkeypatch.delenv("FLY_APP_NAME", raising=False)
    with pytest.raises(CommandError):
        call_command("seed_staff_demo")
    assert not UserProfile.objects.exists()
