from django.contrib import admin
from .models import TeamStanding
from django.contrib import admin
from .models import GoalieStat, SkaterStat, TeamStanding


@admin.register(TeamStanding)
class TeamStandingAdmin(admin.ModelAdmin):
    list_display = (
        "season_id",
        "team_abbrev",
        "division_name",
        "division_sequence",
        "games_played",
        "wins",
        "losses",
        "ot_losses",
        "points",
        "updated_at",
    )
    list_filter = ("season_id", "conference_name", "division_name")
    search_fields = ("team_name", "team_common_name", "team_abbrev")


@admin.register(SkaterStat)
class SkaterStatAdmin(admin.ModelAdmin):
    list_display = (
        "season_id",
        "full_name",
        "current_team",
        "position_code",
        "is_rookie",
        "games_played",
        "goals",
        "assists",
        "points",
    )
    list_filter = ("season_id", "position_code", "is_rookie", "current_team")
    search_fields = ("full_name", "current_team")


@admin.register(GoalieStat)
class GoalieStatAdmin(admin.ModelAdmin):
    list_display = (
        "season_id",
        "full_name",
        "current_team",
        "games_played",
        "wins",
        "save_pct",
        "gaa",
        "shutouts",
    )
    list_filter = ("season_id", "current_team")
    search_fields = ("full_name", "current_team")
