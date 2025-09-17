"""
Management command to update existing users' counties based on their zip codes.

Usage:
    python manage.py update_user_counties [--dry-run]
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from efile.models import update_user_county_from_zip


class Command(BaseCommand):
    help = "Update existing users' counties based on their zip codes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Get users with profiles that have zip codes but no county
        users_with_empty_county = User.objects.filter(
            userprofile__zip_code__isnull=False, userprofile__zip_code__gt="", userprofile__county__in=["", None]
        ).exclude(userprofile__zip_code="")

        total_users = users_with_empty_county.count()

        if total_users == 0:
            self.stdout.write(self.style.SUCCESS("No users found with zip codes and empty counties."))
            return

        self.stdout.write(f"Found {total_users} users with zip codes but no county.")

        updated_count = 0
        failed_count = 0

        for user in users_with_empty_county:
            try:
                zip_code = user.userprofile.zip_code
                self.stdout.write(f"Processing user: {user.email} (zip: {zip_code})")

                if dry_run:
                    # Just show what would happen without making changes
                    from efile.utils.zip_to_county_il import get_county_by_zip

                    county = get_county_by_zip(zip_code)
                    if county:
                        self.stdout.write(f"  Would set county to: {county.lower()}")
                        updated_count += 1
                    else:
                        self.stdout.write(f"  No county found for zip code: {zip_code}")
                        failed_count += 1
                else:
                    # Actually update the user
                    updated = update_user_county_from_zip(user)
                    if updated:
                        user.userprofile.refresh_from_db()
                        self.stdout.write(self.style.SUCCESS(f"  Updated county to: {user.userprofile.county}"))
                        updated_count += 1
                    else:
                        self.stdout.write(self.style.ERROR(f"  Failed to update county for zip: {zip_code}"))
                        failed_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error processing user {user.email}: {e}"))
                failed_count += 1

        # Summary
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDRY RUN SUMMARY: Would update {updated_count} users, {failed_count} could not be updated."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nSUMMARY: Updated {updated_count} users, {failed_count} could not be updated.")
            )
