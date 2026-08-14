from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("efile", "0008_merge_document_prep_and_people_migrations")]

    operations = [
        migrations.AddField(
            model_name="filingdraft",
            name="selected_payment_account_type",
            field=models.CharField(max_length=50, blank=True),
        ),
        migrations.AddField(
            model_name="filingdraft",
            name="quoted_fee_total",
            field=models.CharField(max_length=50, blank=True),
        ),
        migrations.AddField(
            model_name="filingdraft",
            name="quoted_fee_breakdown",
            field=models.JSONField(default=list, blank=True),
        ),
    ]
