from django.core.management.base import BaseCommand, CommandError

from efile.models import UserProfile


class Command(BaseCommand):
    help = "Exclude a designated test account from future reporting; existing anonymous counters are not changed."

    def add_arguments(self, parser):
        parser.add_argument("account_id", type=int)

    def handle(self, *args, **options):
        if not UserProfile.objects.filter(pk=options["account_id"]).update(analytics_excluded=True):
            raise CommandError("Local account not found.")
        self.stdout.write("Account excluded from future reporting.")
