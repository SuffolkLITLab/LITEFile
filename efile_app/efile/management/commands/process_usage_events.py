from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from efile.models import StaffLoginThrottle
from efile.services.analytics import drain_events


class Command(BaseCommand):
    help = "Roll up queued usage events without double-counting. Run at least every minute."

    def handle(self, *args, **options):
        try:
            drain_events()
        except Exception:
            raise CommandError("Usage rollup failed; queued events remain available for retry.") from None
        StaffLoginThrottle.objects.filter(window_started__lt=timezone.now() - timedelta(days=1)).delete()
        self.stdout.write("Usage event batch processed.")
