"""Explicit local-only synthetic fixtures, separate from production collection."""

import os
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from efile.models import FilingDraft, UsageEvent, UserProfile
from efile.services.analytics import count_event
from efile.utils.config_loader import config_loader
from efile.workflow import ExistingCase


class Command(BaseCommand):
    help = "Seed synthetic staff lookup and reporting fixtures; only allowed with DEBUG and a local SQLite database."

    @transaction.atomic
    def handle(self, *args, **options):
        if (
            not settings.DEBUG
            or os.getenv("FLY_APP_NAME")
            or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3"
        ):
            raise CommandError(
                "Demo seeding requires local DEBUG settings and SQLite; it cannot run on deployed settings."
            )
        today = timezone.now().astimezone(UTC).date()
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        occurred_at = datetime(start.year, start.month, 15, 12, tzinfo=UTC)
        for jurisdiction in config_loader.get_available_jurisdictions():
            for number in range(1, 6):
                username = f"litefile-demo-{jurisdiction}-{number}"
                user, created = UserProfile.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": f"{username}@example.invalid",
                        "tyler_jurisdiction": jurisdiction,
                        "analytics_excluded": True,
                    },
                )
                if not created and (
                    user.is_staff or not user.analytics_excluded or user.tyler_jurisdiction != jurisdiction
                ):
                    raise CommandError(
                        "A demo username conflicts with an existing account; no accounts were overwritten."
                    )
                if created:
                    user.set_unusable_password()
                    user.save(update_fields=["password"])
                for kind, existing_case, side in (
                    ("new", ExistingCase.NEW, "initiating"),
                    ("existing", ExistingCase.EXISTING, "responding"),
                ):
                    draft, _ = FilingDraft.objects.get_or_create(
                        user=user, jurisdiction=jurisdiction, existing_case=existing_case
                    )
                    for metric in ("started", "review"):
                        event, _ = UsageEvent.objects.get_or_create(
                            draft=draft,
                            metric=metric,
                            operation="staff_demo",
                            defaults={
                                "occurred_at": occurred_at,
                                "dimensions": {
                                    "filing_kind": kind,
                                    "case_type": "other_or_unknown",
                                    "filer_side": side,
                                    "filing_for": "self",
                                    "zip_code": "unknown",
                                    "usage_frequency": "first",
                                },
                            },
                        )
                        count_event(event.pk)
        self.stdout.write(
            "Synthetic local accounts, drafts, and aggregates ready. No documents or court accounts created."
        )
        self.stdout.write(f"For new fixtures, use report dates {start} through {end} and monthly grouping.")
        self.stdout.write("Existing fixtures are unchanged; repeated runs do not duplicate counts.")
