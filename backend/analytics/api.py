import hmac
import os
from typing import Any, Dict, List, Optional
from django.core.cache import cache
from django.db.models import Max, Q
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from analytics.models import GoalieStat, SkaterStat, TeamStanding
from analytics.services.moneypuck import refresh_all_moneypuck
from analytics.services.nhl_player_profile import fetch_player_profile
from analytics.services.nhl_players import fetch_and_store_players
from analytics.services.nhl_standings import fetch_and_store_standings
from analytics.services.nhl_team_profile import fetch_team_profile

api = NinjaAPI(title="NHL Advanced Analytics API")

CONFERENCE_DIVISIONS = {
    "Eastern": ["Atlantic", "Metropolitan"],
    "Western": ["Central", "Pacific"],
}


# --- Existing Standings Schemas & Endpoint ---


class TeamStandingOut(Schema):
    id: int
    teamAbbrev: str
    teamName: str
    teamCommonName: str
    teamLogo: str
    conferenceName: str
    divisionName: str
    divisionSequence: int
    gp: int
    w: int
    l: int
    otl: int
    pts: int
    pointPctg: float
    gf: int
    ga: int
    diff: int
    l10: str
    strk: str
    homeRecord: str
    awayRecord: str
    homeWinPct: float
    awayWinPct: float
    gfPerGame: float
    gaPerGame: float
    diffPerGame: float


class StandingsResponse(Schema):
    seasonId: str
    seasonLabel: str
    availableSeasons: List[str]
    conferences: Dict[str, Dict[str, List[TeamStandingOut]]]


def format_season_label(season_id: str) -> str:
    if len(season_id) == 8:
        return f"{season_id[:4]}–{season_id[6:]}"
    return season_id


def format_toi(seconds: float) -> str:
    total = int(round(seconds or 0))
    mins, secs = divmod(total, 60)
    return f"{mins}:{secs:02d}"


def serialize_team(row: TeamStanding) -> TeamStandingOut:
    gp = row.games_played or 1
    home_gp = row.home_wins + row.home_losses + row.home_ot_losses
    road_gp = row.road_wins + row.road_losses + row.road_ot_losses

    return TeamStandingOut(
        id=row.id,
        teamAbbrev=row.team_abbrev,
        teamName=row.team_name,
        teamCommonName=row.team_common_name,
        teamLogo=row.team_logo,
        conferenceName=row.conference_name,
        divisionName=row.division_name,
        divisionSequence=row.division_sequence,
        gp=row.games_played,
        w=row.wins,
        l=row.losses,
        otl=row.ot_losses,
        pts=row.points,
        pointPctg=round(row.point_pctg, 3),
        gf=row.goals_for,
        ga=row.goals_against,
        diff=row.goal_differential,
        l10=f"{row.l10_wins}-{row.l10_losses}-{row.l10_ot_losses}",
        strk=f"{row.streak_code}{row.streak_count}" if row.streak_code else "-",
        homeRecord=f"{row.home_wins}-{row.home_losses}-{row.home_ot_losses}",
        awayRecord=f"{row.road_wins}-{row.road_losses}-{row.road_ot_losses}",
        homeWinPct=round((row.home_wins / home_gp) * 100, 1) if home_gp else 0.0,
        awayWinPct=round((row.road_wins / road_gp) * 100, 1) if road_gp else 0.0,
        gfPerGame=round(row.goals_for / gp, 2),
        gaPerGame=round(row.goals_against / gp, 2),
        diffPerGame=round(row.goal_differential / gp, 2),
    )


@api.get("/standings", response=StandingsResponse)
def get_standings(request, season: Optional[str] = None):
    available_seasons = list(
        TeamStanding.objects.values_list("season_id", flat=True)
        .distinct()
        .order_by("-season_id")
    )

    active_season = season or (available_seasons[0] if available_seasons else "")
    queryset = TeamStanding.objects.filter(season_id=active_season).order_by(
        "division_sequence", "-points", "-wins"
    )

    grouped: Dict[str, Dict[str, List[TeamStandingOut]]] = {
        conf: {div: [] for div in divs} for conf, divs in CONFERENCE_DIVISIONS.items()
    }

    for row in queryset:
        if (
            row.conference_name in grouped
            and row.division_name in grouped[row.conference_name]
        ):
            grouped[row.conference_name][row.division_name].append(serialize_team(row))

    return StandingsResponse(
        seasonId=active_season,
        seasonLabel=format_season_label(active_season),
        availableSeasons=available_seasons,
        conferences=grouped,
    )


# --- Players Schemas & Endpoints ---


class SkaterOut(Schema):
    rank: int
    playerId: int
    fullName: str
    teamAbbrev: str
    teamAbbrevs: str
    position: str
    isRookie: bool
    headshotUrl: str
    teamLogo: str
    gp: int
    goals: int
    assists: int
    points: int
    plusMinus: int
    shots: int
    shootingPct: float
    ppPoints: int
    pointsPerGame: float
    toiPerGame: str


class GoalieOut(Schema):
    rank: int
    playerId: int
    fullName: str
    teamAbbrev: str
    teamAbbrevs: str
    headshotUrl: str
    teamLogo: str
    gp: int
    gs: int
    wins: int
    losses: int
    otLosses: int
    record: str
    savePct: float
    savePctDisplay: str
    gaa: float
    shutouts: int
    saves: int
    shotsAgainst: int


class PlayersLeadersResponse(Schema):
    seasonId: str
    seasonLabel: str
    goalieMinGp: int
    topPoints: List[SkaterOut]
    topGoals: List[SkaterOut]
    topGoalies: List[GoalieOut]
    topDefensemen: List[SkaterOut]
    topRookies: List[SkaterOut]


class PlayerCategoryResponse(Schema):
    category: str
    seasonId: str
    seasonLabel: str
    goalieMinGp: int
    totalCount: int
    skaters: List[SkaterOut]
    goalies: List[GoalieOut]


def _active_player_season(season: Optional[str] = None) -> str:
    if season:
        return season
    latest = (
        SkaterStat.objects.values_list("season_id", flat=True)
        .distinct()
        .order_by("-season_id")
        .first()
    )
    return latest or ""


def _goalie_min_gp(season_id: str) -> int:
    max_team_gp = (
        TeamStanding.objects.filter(season_id=season_id).aggregate(
            m=Max("games_played")
        )["m"]
        or GoalieStat.objects.filter(season_id=season_id).aggregate(
            m=Max("games_played")
        )["m"]
        or 0
    )
    # Standard NHL-style qualifier (~30% of team games played, minimum 1)
    return max(1, round(max_team_gp * 0.30))


def _serialize_skaters(rows) -> List[SkaterOut]:
    return [
        SkaterOut(
            rank=idx,
            playerId=r.player_id,
            fullName=r.full_name,
            teamAbbrev=r.current_team,
            teamAbbrevs=r.team_abbrevs,
            position=r.position_code,
            isRookie=r.is_rookie,
            headshotUrl=r.headshot_url,
            teamLogo=r.team_logo,
            gp=r.games_played,
            goals=r.goals,
            assists=r.assists,
            points=r.points,
            plusMinus=r.plus_minus,
            shots=r.shots,
            shootingPct=r.shooting_pct,
            ppPoints=r.pp_points,
            pointsPerGame=r.points_per_game,
            toiPerGame=format_toi(r.toi_per_game),
        )
        for idx, r in enumerate(rows, start=1)
    ]


def _serialize_goalies(rows) -> List[GoalieOut]:
    return [
        GoalieOut(
            rank=idx,
            playerId=r.player_id,
            fullName=r.full_name,
            teamAbbrev=r.current_team,
            teamAbbrevs=r.team_abbrevs,
            headshotUrl=r.headshot_url,
            teamLogo=r.team_logo,
            gp=r.games_played,
            gs=r.games_started,
            wins=r.wins,
            losses=r.losses,
            otLosses=r.ot_losses,
            record=f"{r.wins}-{r.losses}-{r.ot_losses}",
            savePct=r.save_pct,
            savePctDisplay=f"{r.save_pct:.3f}".lstrip("0")
            if r.save_pct < 1
            else f"{r.save_pct:.3f}",
            gaa=r.gaa,
            shutouts=r.shutouts,
            saves=r.saves,
            shotsAgainst=r.shots_against,
        )
        for idx, r in enumerate(rows, start=1)
    ]


@api.get("/players/leaders", response=PlayersLeadersResponse)
def get_player_leaders(request, season: Optional[str] = None):
    active_season = _active_player_season(season)
    min_gp = _goalie_min_gp(active_season)

    skaters = SkaterStat.objects.filter(season_id=active_season)
    goalies = GoalieStat.objects.filter(
        season_id=active_season, games_played__gte=min_gp
    )

    return PlayersLeadersResponse(
        seasonId=active_season,
        seasonLabel=format_season_label(active_season),
        goalieMinGp=min_gp,
        topPoints=_serialize_skaters(
            skaters.order_by("-points", "-goals", "games_played")[:5]
        ),
        topGoals=_serialize_skaters(
            skaters.order_by("-goals", "-points", "games_played")[:5]
        ),
        topGoalies=_serialize_goalies(
            goalies.order_by("-save_pct", "gaa", "-wins")[:5]
        ),
        topDefensemen=_serialize_skaters(
            skaters.filter(position_code="D").order_by(
                "-points", "-goals", "games_played"
            )[:5]
        ),
        topRookies=_serialize_skaters(
            skaters.filter(is_rookie=True).order_by(
                "-points", "-goals", "games_played"
            )[:5]
        ),
    )


@api.get("/players/category/{category}", response=PlayerCategoryResponse)
def get_player_category(
    request,
    category: str,
    season: Optional[str] = None,
    qualified_only: bool = True,
):
    active_season = _active_player_season(season)
    min_gp = _goalie_min_gp(active_season)

    if category == "goalies":
        qs = GoalieStat.objects.filter(season_id=active_season)
        if qualified_only:
            qs = qs.filter(games_played__gte=min_gp)
        rows = list(qs.order_by("-save_pct", "gaa", "-wins"))
        serialized = _serialize_goalies(rows)
        return PlayerCategoryResponse(
            category=category,
            seasonId=active_season,
            seasonLabel=format_season_label(active_season),
            goalieMinGp=min_gp,
            totalCount=len(serialized),
            skaters=[],
            goalies=serialized,
        )

    skaters = SkaterStat.objects.filter(season_id=active_season)
    if category == "points":
        rows = list(skaters.order_by("-points", "-goals", "games_played"))
    elif category == "goals":
        rows = list(skaters.order_by("-goals", "-points", "games_played"))
    elif category == "defensemen":
        rows = list(
            skaters.filter(position_code="D").order_by(
                "-points", "-goals", "games_played"
            )
        )
    elif category == "rookies":
        rows = list(
            skaters.filter(is_rookie=True).order_by("-points", "-goals", "games_played")
        )
    else:
        raise HttpError(404, f"Unknown player category: {category}")

    serialized_skaters = _serialize_skaters(rows)
    return PlayerCategoryResponse(
        category=category,
        seasonId=active_season,
        seasonLabel=format_season_label(active_season),
        goalieMinGp=min_gp,
        totalCount=len(serialized_skaters),
        skaters=serialized_skaters,
        goalies=[],
    )


class PlayerSearchItem(Schema):
    playerId: int
    fullName: str
    teamAbbrev: str
    position: str
    headshotUrl: str
    teamLogo: str
    statSummary: str


class PlayerSearchResponse(Schema):
    query: str
    results: List[PlayerSearchItem]


@api.get("/players/search", response=PlayerSearchResponse)
def search_players(request, q: str = "", limit: int = 12):
    query = q.strip()
    if len(query) < 2:
        return PlayerSearchResponse(query=query, results=[])

    active_season = _active_player_season()
    safe_limit = max(1, min(limit, 30))

    skater_matches = (
        SkaterStat.objects.filter(season_id=active_season)
        .filter(Q(full_name__icontains=query) | Q(current_team__icontains=query))
        .order_by("-points", "-goals")[:safe_limit]
    )

    goalie_matches = (
        GoalieStat.objects.filter(season_id=active_season)
        .filter(Q(full_name__icontains=query) | Q(current_team__icontains=query))
        .order_by("-games_played", "-save_pct")[:safe_limit]
    )

    combined: List[tuple[int, PlayerSearchItem]] = []

    for s in skater_matches:
        priority = 2 if s.full_name.lower().startswith(query.lower()) else 1
        combined.append(
            (
                priority * 1000 + s.points,
                PlayerSearchItem(
                    playerId=s.player_id,
                    fullName=s.full_name,
                    teamAbbrev=s.current_team,
                    position=s.position_code,
                    headshotUrl=s.headshot_url,
                    teamLogo=s.team_logo,
                    statSummary=f"{s.points} PTS ({s.goals}G, {s.assists}A)",
                ),
            )
        )

    for g in goalie_matches:
        priority = 2 if g.full_name.lower().startswith(query.lower()) else 1
        sv_str = (
            f"{g.save_pct:.3f}".lstrip("0") if g.save_pct < 1 else f"{g.save_pct:.3f}"
        )
        combined.append(
            (
                priority * 1000 + g.wins * 3,
                PlayerSearchItem(
                    playerId=g.player_id,
                    fullName=g.full_name,
                    teamAbbrev=g.current_team,
                    position="G",
                    headshotUrl=g.headshot_url,
                    teamLogo=g.team_logo,
                    statSummary=f"{sv_str} SV% · {g.wins}-{g.losses}-{g.ot_losses}",
                ),
            )
        )

    combined.sort(key=lambda item: item[0], reverse=True)
    return PlayerSearchResponse(
        query=query,
        results=[item for _, item in combined[:safe_limit]],
    )


@api.get("/players/{player_id}", response=Dict[str, Any])
def get_player_detail(request, player_id: int):
    try:
        return fetch_player_profile(player_id)
    except ValueError as exc:
        raise HttpError(404, str(exc))


@api.get("/teams/{team_abbrev}", response=Dict[str, Any])
def get_team_detail(request, team_abbrev: str, season: Optional[str] = None):
    try:
        return fetch_team_profile(team_abbrev, season=season)
    except ValueError as exc:
        raise HttpError(404, str(exc))


@api.post("/internal/ingest", response=Dict[str, Any])
def trigger_nightly_ingest(request):
    expected_secret = os.getenv("INGEST_SECRET", "")
    provided_secret = request.headers.get("X-Ingest-Secret", "")

    if not expected_secret or not hmac.compare_digest(provided_secret, expected_secret):
        raise HttpError(403, "Invalid or missing ingest secret.")

    standings_count = fetch_and_store_standings()
    season_id, skater_count, rookie_count, goalie_count = fetch_and_store_players()
    mp_counts = refresh_all_moneypuck(season_id)

    cache.clear()

    return {
        "status": "ok",
        "seasonId": season_id,
        "standingsTeams": standings_count,
        "skaters": skater_count,
        "rookies": rookie_count,
        "goalies": goalie_count,
        "moneyPuck": mp_counts,
    }
