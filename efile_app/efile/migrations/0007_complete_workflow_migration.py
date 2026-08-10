from django.db import migrations, models


STEP_MAPPINGS = {
    "options": "filing_path",
    "upload_first": "upload_documents",
    "case_information": "extraction_review",
    "documents": "organize_documents",
}


def migrate_saved_workflow_positions(apps, schema_editor):
    FilingDraft = apps.get_model("efile", "FilingDraft")
    for old_step, new_step in STEP_MAPPINGS.items():
        FilingDraft.objects.filter(current_step=old_step).update(current_step=new_step)
    FilingDraft.objects.exclude(workflow_version=2).update(workflow_version=2)


class Migration(migrations.Migration):
    dependencies = [("efile", "0006_filingparty_party_type_name")]

    operations = [
        migrations.RunPython(migrate_saved_workflow_positions, migrations.RunPython.noop),
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
                ],
                default="options",
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="filingdraft",
            name="workflow_version",
            field=models.PositiveSmallIntegerField(default=2),
        ),
    ]
