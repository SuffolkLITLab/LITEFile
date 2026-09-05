"""Keep primary filing summaries current when documents are deleted in bulk."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from efile.models import FilingDocument, FilingDraft, sync_primary_filing_type


@receiver(post_delete, sender=FilingDocument)
def synchronize_deleted_document(sender, instance, **kwargs):
    draft = FilingDraft.objects.filter(pk=instance.draft_id).first()
    if draft is not None:
        sync_primary_filing_type(draft)
