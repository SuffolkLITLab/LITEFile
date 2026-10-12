from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("efile", "0046_filingdraft_public_id_unique")]

    operations = [
        migrations.AddField(
            model_name="usageevent",
            name="quantity",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
