from django.core.management.base import BaseCommand

from analytics.services.nhl_players import fetch_and_store_players


class Command(BaseCommand):
    help = "Fetch all NHL skater and goalie stats from api.nhle.com/stats/rest."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=str,
            default=None,
            help="Optional season ID in YYYYYYYY format (e.g. 20262027).",
        )

    def handle(self, *args, **options):
        season_id, skater_count, rookie_count, goalie_count = fetch_and_store_players(
            season_id=options["season"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Ingested {skater_count} skaters ({rookie_count} rookies) and "
                f"{goalie_count} goalies for season {season_id}."
            )
        )
