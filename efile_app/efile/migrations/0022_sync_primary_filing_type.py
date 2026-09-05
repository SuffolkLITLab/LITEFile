from django.db import migrations


def synchronize_primary_types(apps, schema_editor):
    Draft = apps.get_model("efile", "FilingDraft")
    Document = apps.get_model("efile", "FilingDocument")
    database = schema_editor.connection.alias
    for draft in Draft.objects.using(database).iterator():
        lead = Document.objects.using(database).filter(draft_id=draft.pk, role="lead").order_by("sort_order", "pk").first()
        if lead is not None:
            Draft.objects.using(database).filter(pk=draft.pk).update(
                filing_type_code=lead.filing_type_code, filing_type_name=lead.filing_type_name
            )


class Migration(migrations.Migration):
    dependencies = [("efile", "0021_party_is_self")]
    operations = [migrations.RunPython(synchronize_primary_types, migrations.RunPython.noop)]
