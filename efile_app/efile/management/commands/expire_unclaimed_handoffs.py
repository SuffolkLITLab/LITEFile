"""Remove expired unclaimed interview data and its privately stored PDFs."""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from efile.models import FilingDocument, FilingDraft, InterviewHandoff
from efile.services.document_previews import document_storage_keys
from efile.utils.s3_upload_handler import S3UploadHandler


class Command(BaseCommand):
    help = "Preview unclaimed handoffs older than seven days; use --apply to delete them."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be positive.")
        cutoff = timezone.now() - timedelta(days=days)
        receipts = InterviewHandoff.objects.filter(created_at__lt=cutoff, draft__user__isnull=True)
        ids = list(receipts.values_list("draft_id", flat=True))
        if not options["apply"]:
            self.stdout.write(f"Would expire {len(ids)} unclaimed handoffs.")
            return
        handler = S3UploadHandler()
        if ids and not handler._ensure_initialized():
            raise CommandError("Document storage is unavailable; no receipts were deleted.")
        removed = 0
        for draft_id in ids:
            with transaction.atomic():
                draft = FilingDraft.objects.select_for_update().filter(pk=draft_id, user__isnull=True).first()
                if draft is None:
                    continue
                keys = {key for doc in draft.documents.all() for key in document_storage_keys(doc)}
                for key in keys:
                    if (
                        not FilingDocument.objects.filter(Q(s3_key=key) | Q(original_s3_key=key))
                        .exclude(draft=draft)
                        .exists()
                    ):
                        result = handler.delete_file(key)
                        if not result.get("success"):
                            raise CommandError(
                                "Document storage deletion failed; the remaining receipts were retained."
                            )
                draft.delete()
                removed += 1
        self.stdout.write(f"Expired {removed} unclaimed handoffs.")
