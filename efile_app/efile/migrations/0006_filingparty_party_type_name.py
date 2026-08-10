from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("efile", "0005_document_checklist_state")]

    operations = [
        migrations.AddField(
            model_name="filingparty",
            name="party_type_name",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
