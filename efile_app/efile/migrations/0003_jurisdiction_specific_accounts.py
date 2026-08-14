from django.db import migrations, models


def copy_existing_tyler_usernames(apps, schema_editor):
    UserProfile = apps.get_model("efile", "UserProfile")
    for user in UserProfile.objects.exclude(tyler_jurisdiction="").iterator():
        user.tyler_username = user.username
        user.save(update_fields=["tyler_username"])


class Migration(migrations.Migration):
    dependencies = [
        ("efile", "0002_filing_drafts"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="tyler_username",
            field=models.CharField(blank=True, max_length=254),
        ),
        migrations.RunPython(copy_existing_tyler_usernames, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="userprofile",
            constraint=models.UniqueConstraint(
                condition=~models.Q(tyler_username=""),
                fields=("tyler_jurisdiction", "tyler_username"),
                name="unique_tyler_account_per_jurisdiction",
            ),
        ),
    ]
