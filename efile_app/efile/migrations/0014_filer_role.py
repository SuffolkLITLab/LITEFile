from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("efile", "0013_plan_case_link_and_checklist_documents"),
    ]

    operations = [
        migrations.AddField(
            model_name="filingplan",
            name="filer_role",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="filingdraft",
            name="filer_role",
            field=models.CharField(blank=True, max_length=60),
        ),
    ]
