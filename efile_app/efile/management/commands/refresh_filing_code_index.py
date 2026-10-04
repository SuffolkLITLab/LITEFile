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
    help = "Refresh filing search for all jurisdictions, preserving previous snapshots on failure."

    def add_arguments(self, parser):
        parser.add_argument("--jurisdiction", choices=rules()[0]["jurisdictions"])
        parser.add_argument("--interval", type=int, default=0, help="Repeat after this many seconds (0: run once).")
        parser.add_argument("--retry-interval", type=int, default=60, help="Seconds before retrying failed states.")
        parser.add_argument(
            "--cache-dir",
            default=str(Path.home() / ".cache" / "litefile" / "filing-code-cache"),
            help="Compressed court checkpoints, reused for six hours.",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        if interval < 0:
            raise CommandError("Interval must be nonnegative")
        retry_interval = options["retry_interval"]
        if retry_interval <= 0:
            raise CommandError("Retry interval must be positive")
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
                            if options["verbosity"] > 1
                            else None,
                        )
                    self.stdout.write(self.style.SUCCESS(f"{jurisdiction}: indexed {count} filing paths"))
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
