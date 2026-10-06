"""Build complete code snapshots outside the request and release paths."""

import time
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections
from django.test.utils import override_settings
from django.utils import timezone

from efile.services.filing_code_search import current_index, refresh_index, rules


class Command(BaseCommand):
    help = "Sync changed court code exports, preserving previous snapshots on failure."

    def add_arguments(self, parser):
        parser.add_argument("--jurisdiction", choices=rules()[0]["jurisdictions"])
        parser.add_argument("--interval", type=int, default=0, help="Repeat after this many seconds (0: run once).")
        parser.add_argument("--retry-interval", type=int, default=60, help="Seconds before retrying failed states.")
        parser.add_argument(
            "--legacy-crawl", action="store_true", help="Explicitly use the expensive full list-API crawler."
        )
        parser.add_argument(
            "--court",
            action="append",
            default=[],
            help="Re-download this court even if its revision is unchanged (repeatable; needs --jurisdiction).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Download and check changed courts and report path counts, without saving anything.",
        )
        parser.add_argument(
            "--cache-dir",
            default=str(Path.home() / ".cache" / "litefile" / "filing-code-cache"),
            help="Legacy crawler checkpoints, reused for six hours.",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        if interval < 0:
            raise CommandError("Interval must be nonnegative")
        retry_interval = options["retry_interval"]
        if retry_interval <= 0:
            raise CommandError("Retry interval must be positive")
        if options["court"] and not options["jurisdiction"]:
            raise CommandError("--court needs --jurisdiction")
        if (options["court"] or options["dry_run"]) and interval:
            raise CommandError("--court and --dry-run run once; drop --interval")
        jurisdictions = [options["jurisdiction"]] if options["jurisdiction"] else rules()[0]["jurisdictions"]
        while True:
            failures = []
            # The worker sleeps for hours between passes; a connection the
            # database or proxy dropped meanwhile must not fail the next one.
            close_old_connections()
            for jurisdiction in jurisdictions:
                try:
                    if interval:
                        index = current_index(jurisdiction)
                        if index and (timezone.now() - index.refreshed_at).total_seconds() < interval:
                            continue
                    # This dedicated command doesn't serve requests. Rendering
                    # and retaining SQL debug strings for millions of rows is
                    # costly in local development; restore DEBUG after the build.
                    with override_settings(DEBUG=False):
                        count = refresh_index(
                            jurisdiction,
                            cache_dir=options["cache_dir"],
                            progress=lambda court, state=jurisdiction: self.stdout.write(f"{state}: {court}")
                            if options["verbosity"] > 1 or options["dry_run"]
                            else None,
                            force=options["court"],
                            dry_run=options["dry_run"],
                            **({"transport": "legacy"} if options["legacy_crawl"] else {}),
                        )
                    verb = "would synchronize" if options["dry_run"] else "synchronized"
                    self.stdout.write(self.style.SUCCESS(f"{jurisdiction}: {verb} {count} changed filing paths"))
                # DatabaseError covers a lost connection and an overlapping run
                # creating the same jurisdiction's row first (IntegrityError).
                except (requests.RequestException, ValueError, DatabaseError) as error:
                    failures.append(jurisdiction)
                    self.stderr.write(f"{jurisdiction}: refresh failed; previous index kept. {error}")
            if not interval:
                if failures:
                    raise CommandError("Refresh failed: " + ", ".join(failures))
                return
            delay = min(interval, retry_interval) if failures else interval
            if failures:
                self.stderr.write(f"Retrying failed states in {delay} seconds.")
            time.sleep(delay)
