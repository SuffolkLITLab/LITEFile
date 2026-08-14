from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("efile", "0005_document_checklist_state")]

    operations = [
        migrations.AddField(
            model_name="filingdocument",
            name="requested_optional_services",
            field=models.JSONField(default=list, blank=True),
        ),
    ]
