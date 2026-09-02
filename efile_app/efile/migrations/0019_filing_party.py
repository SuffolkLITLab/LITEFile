from django.db import migrations, models


def mark_existing_filers(apps, schema_editor):
    """Every draft made before this field existed filed as the filer's own party.

    The filer's row was the only thing that could be a filing party then, and
    the parties screen refused to continue until it had a party type, so a
    draft mid-flight is answered exactly by that rule.
    """

    FilingParty = apps.get_model("efile", "FilingParty")
    FilingParty.objects.filter(role="filer").exclude(party_type="").update(is_filing_party=True)


class Migration(migrations.Migration):
    dependencies = [
        ("efile", "0018_remembered_ai_choice"),
    ]

    operations = [
        migrations.AddField(
            model_name="filingparty",
            name="is_filing_party",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_filers, migrations.RunPython.noop),
    ]
