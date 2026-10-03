"""Console bootstrap/recovery: never create a password-only staff bypass."""

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from efile.models import UserProfile
from efile.services.privacy import account_sessions


class Command(BaseCommand):
    help = "Provision a staff TOTP authenticator. Deliver the printed secret securely; --reset revokes all sessions."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--reset", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        user = (
            UserProfile.objects.select_for_update()
            .filter(username=options["username"], is_staff=True, is_active=True)
            .first()
        )
        if user is None:
            raise CommandError("An active local staff account is required.")
        devices = TOTPDevice.objects.filter(user=user)
        if devices.exists() and not options["reset"]:
            raise CommandError(
                "An authenticator already exists. Use --reset only after verifying the recovery request."
            )
        if options["reset"]:
            devices.delete()
            Session.objects.filter(pk__in=[s.pk for s in account_sessions(user)]).delete()
        device = TOTPDevice.objects.create(user=user, name="Staff authenticator", confirmed=True)
        self.stdout.write(device.config_url)
