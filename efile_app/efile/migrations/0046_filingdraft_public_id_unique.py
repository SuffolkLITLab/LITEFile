import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    # Kept apart from the backfill: PostgreSQL refuses to alter a table with
    # row updates still pending in the same transaction.
    dependencies = [
        ("efile", "0045_filingdraft_public_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="filingdraft",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
