"""Explicit, one-time environment bootstrap with no default credentials."""

import base64
import binascii
import os
import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from efile.models import UserProfile


class Command(BaseCommand):
    help = "Bootstrap a local-password/TOTP superuser from LITEFILE_STAFF_BOOTSTRAP_* environment variables."

    def handle(self, *args, **options):
        username = os.getenv("LITEFILE_STAFF_BOOTSTRAP_USERNAME", "").strip()
        if not username:
            raise CommandError("Set LITEFILE_STAFF_BOOTSTRAP_USERNAME; there is no default account.")
        existing = UserProfile.objects.filter(username=username).first()
        if existing:
            if not (existing.is_active and existing.is_staff and existing.is_superuser):
                raise CommandError("An incompatible account already exists. Bootstrap cannot promote or overwrite it.")
            if not TOTPDevice.objects.filter(user=existing, confirmed=True).exists():
                raise CommandError(
                    "The account exists without TOTP. Use provision_staff_totp from the trusted console."
                )
            self.stdout.write("Staff account already provisioned; password, roles, and TOTP unchanged.")
            return

        password = os.getenv("LITEFILE_STAFF_BOOTSTRAP_PASSWORD", "")
        if not password:
            raise CommandError("Set LITEFILE_STAFF_BOOTSTRAP_PASSWORD to a unique password; there is no default.")
        email = os.getenv("LITEFILE_STAFF_BOOTSTRAP_EMAIL", "").strip()
        user = UserProfile(username=username, email=email, is_active=True, is_staff=True, is_superuser=True)
        try:
            UserProfile._meta.get_field("username").clean(username, user)
            if email:
                validate_email(email)
            validate_password(password, user=user)
        except ValidationError as error:
            # Never echo supplied values, including a password or TOTP secret.
            raise CommandError(
                "Invalid username, email, or password. Use a valid username and a strong unique password."
            ) from error

        secret = os.getenv("LITEFILE_STAFF_BOOTSTRAP_TOTP_SECRET", "").strip().upper().replace(" ", "").rstrip("=")
        supplied_secret = bool(secret)
        if supplied_secret:
            try:
                key = base64.b32decode(secret + "=" * (-len(secret) % 8))
            except (binascii.Error, ValueError) as error:
                raise CommandError("LITEFILE_STAFF_BOOTSTRAP_TOTP_SECRET must be a valid Base32 secret.") from error
            if not 20 <= len(key) <= 40:
                raise CommandError("Use a TOTP secret containing 20–40 random bytes (32–64 Base32 characters).")
        else:
            key = secrets.token_bytes(20)

        try:
            with transaction.atomic():
                user.set_password(password)
                user.save()
                device = TOTPDevice.objects.create(user=user, name="Staff authenticator", key=key.hex(), confirmed=True)
        except IntegrityError as error:
            raise CommandError(
                "Bootstrap conflicted with another account creation. No credentials were overwritten."
            ) from error

        self.stdout.write(f"Staff superuser created. Sign in at /{settings.LITEFILE_STAFF_PATH}/.")
        if supplied_secret:
            self.stdout.write("TOTP configured from the supplied secret; credentials are not printed.")
        else:
            self.stdout.write("Store this newly generated TOTP setup URI securely; it is printed only on creation:")
            self.stdout.write(device.config_url)
