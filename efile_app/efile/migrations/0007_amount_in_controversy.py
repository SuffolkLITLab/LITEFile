from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("efile", "0006_filingdocument_requested_optional_services")]

    operations = [
        migrations.AddField(
            model_name="filingdraft",
            name="amount_in_controversy",
            field=models.CharField(max_length=50, blank=True),
        ),
        migrations.AddField(
            model_name="filingdocument",
            name="filing_requires_amount_in_controversy",
            field=models.BooleanField(default=False),
        ),
    ]
