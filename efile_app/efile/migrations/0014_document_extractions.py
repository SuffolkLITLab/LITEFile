from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("efile", "0013_archived_cases"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentExtraction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Waiting"),
                            ("processing", "Analyzing"),
                            ("complete", "Complete"),
                            ("failed", "Could not analyze"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("total_pages", models.PositiveIntegerField(blank=True, null=True)),
                ("pages_analyzed", models.PositiveIntegerField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extraction",
                        to="efile.filingdocument",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
