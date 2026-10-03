from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from efile.models import PrivacyRequest, StaffAudit


class Command(BaseCommand):
    help = "Prune resolved request/audit records after the configured retention period; never discard open manifests."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=max(1, settings.LITEFILE_STAFF_REQUEST_RETENTION_DAYS))
        PrivacyRequest.objects.filter(
            status="completed", external_cleanup_pending=False, completed_at__lt=cutoff
        ).delete()
        # Retain audits for unresolved requests even if their processing is old.
        references = PrivacyRequest.objects.values("reference")
        StaffAudit.objects.filter(created_at__lt=cutoff).exclude(reference__in=references).delete()
        self.stdout.write("Resolved staff records pruned; open work retained.")
