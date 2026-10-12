import uuid

from django.db import migrations, models


def assign_public_ids(apps, schema_editor):
    Draft = apps.get_model("efile", "FilingDraft")
    alias = schema_editor.connection.alias
    for draft_id in Draft.objects.using(alias).filter(public_id__isnull=True).values_list("pk", flat=True).iterator():
        Draft.objects.using(alias).filter(pk=draft_id).update(public_id=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [
        ("efile", "0044_filing_identifiers"),
    ]

    operations = [
        migrations.AddField(
            model_name="filingdraft",
            name="public_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(assign_public_ids, migrations.RunPython.noop),
    ]
