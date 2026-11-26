from django.db import models


class TeamStanding(models.Model):
    season_id = models.CharField(max_length=8, db_index=True)  # e.g. "20262027"
    team_abbrev = models.CharField(max_length=5)
    team_name = models.CharField(max_length=100)
    team_common_name = models.CharField(max_length=60)
    team_logo = models.URLField(blank=True)

    conference_name = models.CharField(
        max_length=30, db_index=True
    )  # Eastern / Western
    division_name = models.CharField(
        max_length=30, db_index=True
    )  # Atlantic / Metropolitan / Central / Pacific
    division_sequence = models.PositiveSmallIntegerField(default=1)

    games_played = models.PositiveSmallIntegerField(default=0)
    wins = models.PositiveSmallIntegerField(default=0)
    losses = models.PositiveSmallIntegerField(default=0)
    ot_losses = models.PositiveSmallIntegerField(default=0)
    points = models.PositiveSmallIntegerField(default=0)
    point_pctg = models.FloatField(default=0.0)

    goals_for = models.PositiveSmallIntegerField(default=0)
    goals_against = models.PositiveSmallIntegerField(default=0)
    goal_differential = models.SmallIntegerField(default=0)

    l10_wins = models.PositiveSmallIntegerField(default=0)
    l10_losses = models.PositiveSmallIntegerField(default=0)
    l10_ot_losses = models.PositiveSmallIntegerField(default=0)

    home_wins = models.PositiveSmallIntegerField(default=0)
    home_losses = models.PositiveSmallIntegerField(default=0)
    home_ot_losses = models.PositiveSmallIntegerField(default=0)

    road_wins = models.PositiveSmallIntegerField(default=0)
    road_losses = models.PositiveSmallIntegerField(default=0)
    road_ot_losses = models.PositiveSmallIntegerField(default=0)

    streak_code = models.CharField(max_length=4, blank=True)  # W, L, OT
    streak_count = models.PositiveSmallIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["season_id", "team_abbrev"],
                name="unique_team_standing_per_season",
            )
        ]
        ordering = ["division_name", "division_sequence", "-points", "-wins"]

    def __str__(self) -> str:
        return f"{self.season_id} - {self.team_abbrev} ({self.points} pts)"


class SkaterStat(models.Model):
    season_id = models.CharField(max_length=8, db_index=True)
    player_id = models.IntegerField(db_index=True)
    full_name = models.CharField(max_length=120)
    team_abbrevs = models.CharField(max_length=30)
    current_team = models.CharField(max_length=5, db_index=True)
    position_code = models.CharField(max_length=4, db_index=True)  # C, L, R, D
    is_rookie = models.BooleanField(default=False, db_index=True)
    headshot_url = models.URLField(blank=True)
    team_logo = models.URLField(blank=True)

    games_played = models.PositiveSmallIntegerField(default=0)
    goals = models.PositiveSmallIntegerField(default=0)
    assists = models.PositiveSmallIntegerField(default=0)
    points = models.PositiveSmallIntegerField(default=0)
    plus_minus = models.SmallIntegerField(default=0)
    shots = models.PositiveSmallIntegerField(default=0)
    shooting_pct = models.FloatField(default=0.0)
    pp_points = models.PositiveSmallIntegerField(default=0)
    points_per_game = models.FloatField(default=0.0)
    toi_per_game = models.FloatField(default=0.0)  # seconds

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["season_id", "player_id"],
                name="unique_skater_stat_per_season",
            )
        ]
        ordering = ["-points", "-goals", "games_played"]

    def __str__(self) -> str:
        return f"{self.season_id} - {self.full_name} ({self.points} pts)"


class GoalieStat(models.Model):
    season_id = models.CharField(max_length=8, db_index=True)
    player_id = models.IntegerField(db_index=True)
    full_name = models.CharField(max_length=120)
    team_abbrevs = models.CharField(max_length=30)
    current_team = models.CharField(max_length=5, db_index=True)
    headshot_url = models.URLField(blank=True)
    team_logo = models.URLField(blank=True)

    games_played = models.PositiveSmallIntegerField(default=0)
    games_started = models.PositiveSmallIntegerField(default=0)
    wins = models.PositiveSmallIntegerField(default=0)
    losses = models.PositiveSmallIntegerField(default=0)
    ot_losses = models.PositiveSmallIntegerField(default=0)
    save_pct = models.FloatField(default=0.0)
    gaa = models.FloatField(default=0.0)
    shutouts = models.PositiveSmallIntegerField(default=0)
    saves = models.PositiveIntegerField(default=0)
    shots_against = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["season_id", "player_id"],
                name="unique_goalie_stat_per_season",
            )
        ]
        ordering = ["-save_pct", "gaa", "-wins"]

    def __str__(self) -> str:
        return f"{self.season_id} - {self.full_name} ({self.save_pct:.3f})"
