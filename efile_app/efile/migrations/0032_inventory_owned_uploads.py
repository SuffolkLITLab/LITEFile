"""Inventory current and historical application-owned objects without S3 access."""

from django.db import migrations


def inventory_uploads(apps, schema_editor):
    Document = apps.get_model("efile", "FilingDocument")
    Draft = apps.get_model("efile", "FilingDraft")
    Upload = apps.get_model("efile", "StoredUpload")
    alias = schema_editor.connection.alias
    batch = []

    def add(draft_id, keys):
        for key in keys:
            if isinstance(key, str) and key:
                batch.append(Upload(draft_id=draft_id, key=key))
        if len(batch) >= 1000:
            Upload.objects.using(alias).bulk_create(batch, ignore_conflicts=True)
            batch.clear()

    for draft_id, current, original in Document.objects.using(alias).values_list("draft_id", "s3_key", "original_s3_key").iterator():
        add(draft_id, [current, original])
    for draft_id, snapshot in Draft.objects.using(alias).values_list("pk", "submission_snapshot").iterator():
        if not isinstance(snapshot, dict):
            continue
        documents = snapshot.get("documents", [])
        if not isinstance(documents, list):
            continue
        for document in documents:
            if isinstance(document, dict):
                add(draft_id, [document.get("s3_key"), document.get("original_s3_key")])
    if batch:
        Upload.objects.using(alias).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("efile", "0031_staff_privacy_analytics")]
    operations = [migrations.RunPython(inventory_uploads, migrations.RunPython.noop)]
