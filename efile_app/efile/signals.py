"""Keep primary filing summaries current when documents are deleted in bulk."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from efile.models import FilingDocument, FilingDraft, sync_primary_filing_type


@receiver(post_delete, sender=FilingDocument)
def synchronize_deleted_document(sender, instance, **kwargs):
    draft = FilingDraft.objects.filter(pk=instance.draft_id).first()
    if draft is not None:
        sync_primary_filing_type(draft)


# Metadata provenance is recorded for ordinary filing screens as well as the
# handoff screen. Source suggestions stay in the receipt when a filer overrides
# them. Pure summary synchronization intentionally uses QuerySet.update instead.
from django.db.models.signals import post_save, pre_save  # noqa: E402

from efile.models import FilingParty  # noqa: E402

_METADATA_FIELDS = {
    FilingDraft: ("court_code", "case_category_code", "case_type_code", "case_subtype_code"),
    FilingDocument: ("filing_type_code", "document_type_code", "filing_component_code", "requested_optional_services"),
    FilingParty: ("party_type",),
}


@receiver(pre_save, sender=FilingDraft)
@receiver(pre_save, sender=FilingDocument)
@receiver(pre_save, sender=FilingParty)
def remember_metadata_before_edit(sender, instance, **kwargs):
    if not instance.pk:
        instance._metadata_before = None
        return
    instance._metadata_before = sender.objects.filter(pk=instance.pk).values(*_METADATA_FIELDS[sender]).first()


@receiver(post_save, sender=FilingDraft)
@receiver(post_save, sender=FilingDocument)
@receiver(post_save, sender=FilingParty)
def record_metadata_edit(sender, instance, update_fields=None, **kwargs):
    from efile.services.handoff import receipt_for, record

    before = getattr(instance, "_metadata_before", None)
    if before is None or getattr(instance, "_metadata_kind", "") == "live_resolution":
        return
    changes = {
        field: {"before": previous, "after": getattr(instance, field)}
        for field, previous in before.items()
        if (update_fields is None or field in update_fields) and previous != getattr(instance, field)
    }
    if not changes:
        return
    draft = instance if sender is FilingDraft else instance.draft
    if not draft.correction_of_id and not receipt_for(draft):
        return
    for field, value in changes.items():
        prefix = (
            "" if sender is FilingDraft else f"{'documents' if sender is FilingDocument else 'parties'}.{instance.pk}."
        )
        path = prefix + field
        record(draft, path, "user_edit", value)
        if value["after"] and path in draft.correction_fields:
            draft.correction_fields = [item for item in draft.correction_fields if item != path]
            FilingDraft.objects.filter(pk=draft.pk).update(correction_fields=draft.correction_fields)
