from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("efile", "0003_branch_aware_workflow")]

    operations = [
        migrations.AddField(
            model_name="filingdraft",
            name="case_title",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
