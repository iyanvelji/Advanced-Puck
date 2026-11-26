import json
import httpx
from django.db import transaction
from analytics.models import GoalieStat, SkaterStat, TeamStanding

NHL_STATS_API_BASE = "https://api.nhle.com/stats/rest/en"
NHL_WEB_API_BASE = "https://api-web.nhle.com"
PAGE_SIZE = 100


def _resolve_season_id(season_id: str | None = None) -> str:
    if season_id:
        return str(season_id)

    latest = (
        TeamStanding.objects.values_list("season_id", flat=True)
        .distinct()
        .order_by("-season_id")
        .first()
    )
    if latest:
        return latest

    with httpx.Client(
        base_url=NHL_WEB_API_BASE, follow_redirects=True, timeout=15.0
    ) as client:
        resp = client.get("/v1/standings/now")
        resp.raise_for_status()
        rows = resp.json().get("standings", [])
        if rows and rows[0].get("seasonId"):
            return str(rows[0]["seasonId"])

    raise ValueError("Could not determine active NHL season ID.")


def _fetch_all_pages(
    client: httpx.Client,
    endpoint: str,
    cayenne_exp: str,
    sort_spec: list[dict[str, str]],
) -> list[dict]:
    """
    Paginate through api.nhle.com/stats/rest endpoints in batches of 100
    until every matching record is retrieved, deduplicated by playerId.
    """
    all_rows_by_id: dict[int, dict] = {}
    start = 0
    sort_param = json.dumps(sort_spec)

    while True:
        resp = client.get(
            endpoint,
            params={
                "isAggregate": "false",
                "isGame": "false",
                "cayenneExp": cayenne_exp,
                "sort": sort_param,
                "start": start,
                "limit": PAGE_SIZE,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("data", [])
        total = int(payload.get("total") or 0)

        if not batch:
            break

        for row in batch:
            pid = row.get("playerId")
            if pid is not None:
                all_rows_by_id[int(pid)] = row

        start += len(batch)
        if total and start >= total:
            break
        if len(batch) < PAGE_SIZE:
            break

    return list(all_rows_by_id.values())


def _extract_current_team(team_abbrevs: str) -> str:
    if not team_abbrevs:
        return ""
    parts = [p.strip() for p in team_abbrevs.split(",") if p.strip()]
    return parts[-1] if parts else ""


def _headshot_url(season_id: str, team_abbrev: str, player_id: int) -> str:
    if team_abbrev:
        return f"https://assets.nhle.com/mugs/nhl/{season_id}/{team_abbrev}/{player_id}.png"
    return f"https://assets.nhle.com/mugs/nhl/latest/{player_id}.png"


def _team_logo_url(team_abbrev: str) -> str:
    if not team_abbrev:
        return ""
    return f"https://assets.nhle.com/logos/nhl/svg/{team_abbrev}_dark.svg"


def _fetch_rookie_ids(client: httpx.Client, season_id: str) -> set[int]:
    """Fetch all rookie player IDs for the season across all pages."""
    expressions = [
        f'seasonId={season_id} and gameTypeId=2 and isRookie="1"',
        f"seasonId={season_id} and gameTypeId=2 and isRookie=1",
    ]
    sort_spec = [
        {"property": "points", "direction": "DESC"},
        {"property": "playerId", "direction": "ASC"},
    ]
    for expr in expressions:
        try:
            rows = _fetch_all_pages(client, "/skater/summary", expr, sort_spec)
            if rows:
                return {int(row["playerId"]) for row in rows if row.get("playerId")}
        except httpx.HTTPError:
            continue
    return set()


def fetch_and_store_players(season_id: str | None = None) -> tuple[str, int, int, int]:
    """
    Fetch every regular-season skater, rookie, and goalie from
    api.nhle.com/stats/rest using full pagination and bulk upsert into the DB.
    """
    active_season = _resolve_season_id(season_id)
    base_expr = f"seasonId={active_season} and gameTypeId=2"

    skater_sort = [
        {"property": "points", "direction": "DESC"},
        {"property": "goals", "direction": "DESC"},
        {"property": "playerId", "direction": "ASC"},
    ]
    goalie_sort = [
        {"property": "savePct", "direction": "DESC"},
        {"property": "playerId", "direction": "ASC"},
    ]

    with httpx.Client(
        base_url=NHL_STATS_API_BASE,
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        skater_rows = _fetch_all_pages(
            client, "/skater/summary", base_expr, skater_sort
        )
        rookie_ids = _fetch_rookie_ids(client, active_season)
        goalie_rows = _fetch_all_pages(
            client, "/goalie/summary", base_expr, goalie_sort
        )

    skater_objects: list[SkaterStat] = []
    for item in skater_rows:
        player_id = item.get("playerId")
        if not player_id:
            continue
        team_abbrevs = str(item.get("teamAbbrevs") or "")
        current_team = _extract_current_team(team_abbrevs)
        gp = int(item.get("gamesPlayed") or 0)
        pts = int(item.get("points") or 0)
        raw_shot_pct = float(item.get("shootingPct") or 0.0)
        shot_pct_display = (
            round(raw_shot_pct * 100, 1)
            if raw_shot_pct <= 1.0
            else round(raw_shot_pct, 1)
        )

        skater_objects.append(
            SkaterStat(
                season_id=active_season,
                player_id=int(player_id),
                full_name=str(item.get("skaterFullName") or "Unknown"),
                team_abbrevs=team_abbrevs,
                current_team=current_team,
                position_code=str(item.get("positionCode") or ""),
                is_rookie=int(player_id) in rookie_ids,
                headshot_url=_headshot_url(active_season, current_team, int(player_id)),
                team_logo=_team_logo_url(current_team),
                games_played=gp,
                goals=int(item.get("goals") or 0),
                assists=int(item.get("assists") or 0),
                points=pts,
                plus_minus=int(item.get("plusMinus") or 0),
                shots=int(item.get("shots") or 0),
                shooting_pct=shot_pct_display,
                pp_points=int(item.get("ppPoints") or 0),
                points_per_game=round(pts / gp, 2) if gp else 0.0,
                toi_per_game=float(item.get("timeOnIcePerGame") or 0.0),
            )
        )

    goalie_objects: list[GoalieStat] = []
    for item in goalie_rows:
        player_id = item.get("playerId")
        if not player_id:
            continue
        team_abbrevs = str(item.get("teamAbbrevs") or "")
        current_team = _extract_current_team(team_abbrevs)

        goalie_objects.append(
            GoalieStat(
                season_id=active_season,
                player_id=int(player_id),
                full_name=str(item.get("goalieFullName") or "Unknown"),
                team_abbrevs=team_abbrevs,
                current_team=current_team,
                headshot_url=_headshot_url(active_season, current_team, int(player_id)),
                team_logo=_team_logo_url(current_team),
                games_played=int(item.get("gamesPlayed") or 0),
                games_started=int(item.get("gamesStarted") or 0),
                wins=int(item.get("wins") or 0),
                losses=int(item.get("losses") or 0),
                ot_losses=int(item.get("otLosses") or 0),
                save_pct=round(float(item.get("savePct") or 0.0), 4),
                gaa=round(float(item.get("goalsAgainstAverage") or 0.0), 2),
                shutouts=int(item.get("shutouts") or 0),
                saves=int(item.get("saves") or 0),
                shots_against=int(item.get("shotsAgainst") or 0),
                goals_against=int(item.get("goalsAgainst") or 0),
            )
        )

    with transaction.atomic():
        if skater_objects:
            SkaterStat.objects.bulk_create(
                skater_objects,
                update_conflicts=True,
                unique_fields=["season_id", "player_id"],
                update_fields=[
                    "full_name",
                    "team_abbrevs",
                    "current_team",
                    "position_code",
                    "is_rookie",
                    "headshot_url",
                    "team_logo",
                    "games_played",
                    "goals",
                    "assists",
                    "points",
                    "plus_minus",
                    "shots",
                    "shooting_pct",
                    "pp_points",
                    "points_per_game",
                    "toi_per_game",
                ],
            )

        if goalie_objects:
            GoalieStat.objects.bulk_create(
                goalie_objects,
                update_conflicts=True,
                unique_fields=["season_id", "player_id"],
                update_fields=[
                    "full_name",
                    "team_abbrevs",
                    "current_team",
                    "headshot_url",
                    "team_logo",
                    "games_played",
                    "games_started",
                    "wins",
                    "losses",
                    "ot_losses",
                    "save_pct",
                    "gaa",
                    "shutouts",
                    "saves",
                    "shots_against",
                    "goals_against",
                ],
            )

    return active_season, len(skater_objects), len(rookie_ids), len(goalie_objects)
