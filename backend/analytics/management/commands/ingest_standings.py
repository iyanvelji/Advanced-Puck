from django.core.management.base import BaseCommand
from analytics.services.nhl_standings import fetch_and_store_standings


class Command(BaseCommand):
    help = "Fetch NHL standings from api-web.nhle.com and store them in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Optional YYYY-MM-DD date to ingest historical standings.",
        )

    def handle(self, *args, **options):
        target_date = options["date"]
        count = fetch_and_store_standings(target_date=target_date)
        label = target_date or "now"
        self.stdout.write(
            self.style.SUCCESS(f"Successfully ingested {count} teams for '{label}'.")
        )
