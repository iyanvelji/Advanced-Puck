from django.core.management.base import BaseCommand
from analytics.models import TeamStanding
from analytics.services.moneypuck import refresh_all_moneypuck


class Command(BaseCommand):
    help = (
        "Download and cache official MoneyPuck season CSVs (skaters, goalies, teams)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=str,
            default=None,
            help="Season ID in YYYYYYYY format (defaults to latest season in DB).",
        )

    def handle(self, *args, **options):
        season_id = options["season"] or (
            TeamStanding.objects.values_list("season_id", flat=True)
            .distinct()
            .order_by("-season_id")
            .first()
            or "20262027"
        )
        counts = refresh_all_moneypuck(season_id)
        self.stdout.write(
            self.style.SUCCESS(
                f"Cached MoneyPuck {season_id[:4]} CSVs: "
                f"{counts['skaters']} skater rows, {counts['goalies']} goalie rows, "
                f"{counts['teams']} team rows."
            )
        )
