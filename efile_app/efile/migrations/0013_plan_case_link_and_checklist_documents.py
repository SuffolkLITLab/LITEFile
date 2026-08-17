from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("efile", "0012_merge_filing_plans_and_jurisdiction_accounts_and_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="filingplan",
            name="case_tracking_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="filingplan",
            name="docket_number",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="filingplan",
            name="case_title",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="filingdocument",
            name="checklist_item_id",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
