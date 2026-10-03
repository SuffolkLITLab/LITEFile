from django.core.management.base import BaseCommand

from efile.models import PrivacyRequest
from efile.services.privacy import process_request


class Command(BaseCommand):
    help = "Resume previously confirmed deletion work. Preview by default; --apply retries storage failures/interrupted processing."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        requests = PrivacyRequest.objects.filter(
            status__in=["processing", "attention"], outcome__in=["", "storage_failed"]
        )
        for item in requests.order_by("created_at"):
            if not item.verified_at or not item.operator_id:
                continue
            if not options["apply"]:
                self.stdout.write(f"Pending confirmed request {item.reference}.")
                continue
            try:
                result = process_request(item.pk, item.operator)
            except Exception:
                self.stderr.write(f"Request {item.reference} requires operator attention.")
            else:
                self.stdout.write(f"Request {item.reference}: {result.status} / {result.outcome}.")
