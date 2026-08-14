from django.db import migrations, models


def normalize_existing_case(apps, schema_editor):
    FilingDraft = apps.get_model("efile", "FilingDraft")
    FilingDraft.objects.filter(existing_case="no").update(existing_case="new")
    FilingDraft.objects.filter(existing_case__in=["yes", "responding"]).update(existing_case="existing")


class Migration(migrations.Migration):
    dependencies = [("efile", "0002_filing_drafts")]

    operations = [
        migrations.RunPython(normalize_existing_case, migrations.RunPython.noop),
        migrations.AddField(
            model_name="filingdraft",
            name="workflow_version",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="filingdraft",
            name="existing_case",
            field=models.CharField(
                blank=True,
                choices=[("new", "New"), ("existing", "Existing"), ("unsure", "Unsure")],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="filingdraft",
            name="current_step",
            field=models.CharField(
                choices=[
                    ("options", "Options"),
                    ("filing_path", "Filing"),
                    ("upload_documents", "Upload documents"),
                    ("extraction_review", "Confirm filing"),
                    ("case_lookup", "Find your case"),
                    ("case_confirmation", "Confirm your case"),
                    ("document_checklist", "Check documents"),
                    ("organize_documents", "Organize documents"),
                    ("your_information", "Your information"),
                    ("parties", "People in this filing"),
                    ("party_details", "Person details"),
                    ("case_questions", "Case questions"),
                    ("payment", "Fees"),
                    ("review", "Review"),
                    ("confirmation", "Confirmation"),
                    ("upload_first", "Upload lead document"),
                    ("case_information", "Case information"),
                    ("documents", "Documents"),
                ],
                default="options",
                max_length=64,
            ),
        ),
    ]
