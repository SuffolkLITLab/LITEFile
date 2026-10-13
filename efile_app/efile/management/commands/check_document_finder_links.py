"""Report document finder links that no longer open."""

import requests
from django.core.management.base import BaseCommand, CommandError

from efile.services.document_finder import configured_links, has_document_finder
from efile.utils.config_loader import config_loader

TIMEOUT_SECONDS = 20
# Some court sites refuse requests that do not look like a browser.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LITEFile link check)"}


class Command(BaseCommand):
    help = "Check that every guided interview, form, and help link in the document finder still opens."

    def add_arguments(self, parser):
        parser.add_argument("--jurisdiction", choices=config_loader.get_available_jurisdictions())

    def handle(self, *args, jurisdiction=None, **options):
        jurisdictions = [jurisdiction] if jurisdiction else config_loader.get_available_jurisdictions()
        checked = {}
        broken = 0
        for code in jurisdictions:
            if not has_document_finder(code):
                continue
            for where, resource in configured_links(code):
                url = resource["url"]
                if url not in checked:
                    checked[url] = self._status(url)
                status = checked[url]
                if status != 200:
                    broken += 1
                    self.stdout.write(f"{code} {where}: {status} {resource['label']} <{url}>")
        self.stdout.write(f"Checked {len(checked)} links; {broken} did not open.")
        if broken:
            raise CommandError("Some document finder links did not open.")

    @staticmethod
    def _status(url):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS, allow_redirects=True, stream=True)
            response.close()
        except requests.RequestException as error:
            return type(error).__name__
        return response.status_code
