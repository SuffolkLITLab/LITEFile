from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("efile", "0004_filingdraft_case_title")]

    operations = [
        migrations.AddField(
            model_name="filingdraft",
            name="document_checklist_acknowledged",
            field=models.BooleanField(default=False),
        ),
    ]
