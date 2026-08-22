import logging
import time

from django.core.management.base import BaseCommand

from efile.services.document_extractions import (
    claim_next_extraction,
    process_document_extraction,
    record_extraction_failure,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process queued lead-document extraction jobs"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args, **options):
        while True:
            job = claim_next_extraction()
            if job is None:
                if options["once"]:
                    return
                time.sleep(max(0.1, options["poll_interval"]))
                continue

            try:
                process_document_extraction(job.pk)
            except Exception as error:
                logger.exception("Document extraction job %s failed", job.pk)
                record_extraction_failure(job.pk, error)

            if options["once"]:
                return
