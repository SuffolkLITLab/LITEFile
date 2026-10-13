"""Report all generated interview documents, exclusions, and crosswalk gaps."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from efile.services.guided_interview_forms import DATA_DIR, inventory_report, load_inventory


class Command(BaseCommand):
    help = "Audit every repository/output in the VT/IL guided-interview inventory against the form crosswalk."

    def add_arguments(self, parser):
        parser.add_argument("--directory", type=Path, default=DATA_DIR)
        parser.add_argument("--output", type=Path, help="Write the complete per-document JSON report here.")

    def handle(self, *args, **options):
        try:
            report = inventory_report(*load_inventory(options["directory"]))
        except (OSError, KeyError, ValueError) as error:
            raise CommandError(str(error)) from error
        if options["output"]:
            options["output"].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        self.stdout.write(json.dumps(report["states"], indent=2))
        for error in report["inventory_errors"]:
            self.stderr.write(error)
        if report["inventory_errors"]:
            raise CommandError("The source inventory is incomplete or inconsistent; see the errors above.")
        self.stdout.write("Inventory checks passed. Mapping counts do not establish live court coverage.")
