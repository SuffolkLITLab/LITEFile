from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("efile", "0014_document_extractions")]

    operations = [
        migrations.AddField(
            model_name="documentextraction",
            name="evidence",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="documentextraction",
            name="classification",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="documentextraction",
            name="analysis_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
