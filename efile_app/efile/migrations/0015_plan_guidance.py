from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("efile", "0014_filer_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="filingplan",
            name="guidance",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
