from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any
import httpx
from django.core.cache import cache
from analytics.models import TeamStanding
from analytics.services.moneypuck import get_team_moneypuck

NHL_WEB_API_BASE = "https://api-web.nhle.com"
NHL_STATS_API_BASE = "https://api.nhle.com/stats/rest/en"
CACHE_TTL_SECONDS = 600
TEAM_DIRECTORY_TTL = 86400


def _fmt_season(season_id: int | str) -> str:
    s = str(season_id or "")
    return f"{s[:4]}–{s[6:]}" if len(s) == 8 else s


def _fmt_toi(val: float | int | str | None) -> str:
    if val is None or val == "":
        return "—"
    if isinstance(val, str) and ":" in val:
        return val
    try:
        total = int(round(float(val)))
        mins, secs = divmod(total, 60)
        return f"{mins}:{secs:02d}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(val: float | int | None, decimals: int = 1) -> str:
    if val is None:
        return "—"
    num = float(val)
    if abs(num) <= 1.0:
        num *= 100.0
    return f"{num:.{decimals}f}%"


def _fmt_sv_pct(val: float | int | None) -> str:
    if val is None:
        return "—"
    num = float(val)
    if num > 1.0:
        num /= 100.0
    return f"{num:.3f}".lstrip("0") if num < 1.0 else f"{num:.3f}"


def _fmt_num(val: float | int | None, decimals: int = 2, signed: bool = False) -> str:
    if val is None:
        return "—"
    num = float(val)
    if decimals == 0:
        i = int(round(num))
        return f"+{i}" if signed and i > 0 else str(i)
    return f"{num:+.{decimals}f}" if signed else f"{num:.{decimals}f}"


def _fmt_height(inches: int | None) -> str:
    if not inches:
        return "—"
    feet, rem = divmod(int(inches), 12)
    return f"{feet}'{rem}\""


def _calc_age(birth_date_str: str | None) -> int | None:
    if not birth_date_str:
        return None
    try:
        dob = datetime.strptime(birth_date_str[:10], "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except ValueError:
        return None


def _ordinal(n: int | None) -> str | None:
    if n is None:
        return None
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _normalize_percentile(val: Any) -> int | None:
    if val is None:
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if 0.0 < num <= 1.0:
        num *= 100.0
    return max(0, min(99, int(round(num))))


def _extract_metric_value(obj: Any, unit_key: str = "imperial") -> float | None:
    if obj is None:
        return None
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, dict):
        for key in (unit_key, "value", "default", "measurement"):
            val = obj.get(key)
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, dict):
                nested = _extract_metric_value(val, unit_key)
                if nested is not None:
                    return nested
    return None


def _safe_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
    except (httpx.HTTPError, ValueError):
        pass
    return {}


def _get_team_directory() -> dict[str, dict[str, Any]]:
    """Map triCode (e.g. 'OTT') -> {'id': 9, 'fullName': 'Ottawa Senators', ...}."""
    cache_key = "nhl_team_directory_v1"
    cached = cache.get(cache_key)
    if cached:
        return cached

    payload = _safe_get_json(f"{NHL_STATS_API_BASE}/team")
    directory: dict[str, dict[str, Any]] = {}
    for row in payload.get("data") or []:
        code = str(row.get("triCode") or "").upper()
        if code and row.get("id") is not None:
            directory[code] = {
                "id": int(row["id"]),
                "fullName": str(row.get("fullName") or code),
                "franchiseId": row.get("franchiseId"),
            }

    if directory:
        cache.set(cache_key, directory, TEAM_DIRECTORY_TTL)
    return directory


def _fetch_league_team_report(report: str, season_id: str) -> list[dict[str, Any]]:
    """Fetch all 32 teams for a given stats report (cached across team pages)."""
    cache_key = f"nhl_team_report_v1_{season_id}_{report}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    payload = _safe_get_json(
        f"{NHL_STATS_API_BASE}/team/{report}",
        params={
            "isAggregate": "false",
            "isGame": "false",
            "cayenneExp": f"seasonId={season_id} and gameTypeId=2",
            "limit": 100,
        },
    )
    rows = payload.get("data") or []
    if rows:
        cache.set(cache_key, rows, CACHE_TTL_SECONDS)
    return rows


def _find_team_row(
    rows: list[dict[str, Any]], team_id: int | None, team_name: str
) -> dict[str, Any]:
    if team_id is not None:
        for r in rows:
            if r.get("teamId") == team_id:
                return r
    lower_name = team_name.lower()
    for r in rows:
        if str(r.get("teamFullName") or "").lower() == lower_name:
            return r
    return {}


def _league_rank(
    rows: list[dict[str, Any]],
    team_id: int | None,
    field: str,
    higher_is_better: bool = True,
) -> int | None:
    if team_id is None or not rows:
        return None
    scored: list[tuple[int, float]] = []
    for r in rows:
        tid = r.get("teamId")
        val = r.get(field)
        if tid is not None and val is not None:
            try:
                scored.append((int(tid), float(val)))
            except (TypeError, ValueError):
                continue
    if not scored:
        return None
    scored.sort(key=lambda x: x[1], reverse=higher_is_better)
    for idx, (tid, _) in enumerate(scored, start=1):
        if tid == team_id:
            return idx
    return None


def _fmt_record(w: Any, l: Any, otl: Any) -> str:
    if w is None and l is None:
        return "—"
    return f"{int(w or 0)}-{int(l or 0)}-{int(otl or 0)}"


def _parse_team_edge(
    edge_detail: dict[str, Any], edge_comparison: dict[str, Any]
) -> dict[str, Any] | None:
    if not edge_detail and not edge_comparison:
        return None

    metrics: list[dict[str, Any]] = []

    skating_speed = (
        edge_detail.get("skatingSpeed") or edge_comparison.get("skatingSpeed") or {}
    )
    speed_max = skating_speed.get("speedMax") or {}
    bursts_22 = skating_speed.get("burstsOver22") or {}
    bursts_20 = skating_speed.get("bursts20To22") or {}

    shot_speed = edge_detail.get("shotSpeed") or edge_comparison.get("shotSpeed") or {}
    top_shot = shot_speed.get("topShotSpeed") or shot_speed
    shots_90 = (
        shot_speed.get("shotAttemptsOver90") or shot_speed.get("shotsOver90") or {}
    )

    distance = (
        edge_detail.get("skatingDistance")
        or edge_comparison.get("skatingDistance")
        or {}
    )
    dist_total = distance.get("total") or distance

    def _add_metric(label: str, obj: Any, unit: str = "", fmt: str = ".2f") -> None:
        val = _extract_metric_value(obj, "imperial")
        if val is None:
            return
        rank = obj.get("rank") if isinstance(obj, dict) else None
        pct = (
            _normalize_percentile(obj.get("percentile"))
            if isinstance(obj, dict)
            else None
        )
        if pct is None and isinstance(rank, (int, float)) and 1 <= rank <= 32:
            pct = max(1, min(99, int(round((33 - rank) / 32 * 100))))
        avg_val = (
            _extract_metric_value(obj.get("leagueAvg"), "imperial")
            if isinstance(obj, dict)
            else None
        )
        formatted = f"{int(round(val))}{unit}" if fmt == "d" else f"{val:{fmt}}{unit}"
        avg_formatted = None
        if avg_val is not None:
            avg_formatted = (
                f"{avg_val:.1f}{unit}" if fmt == "d" else f"{avg_val:{fmt}}{unit}"
            )
        metrics.append(
            {
                "label": label,
                "value": formatted,
                "rank": int(rank) if isinstance(rank, (int, float)) else None,
                "percentile": pct,
                "leagueAvg": avg_formatted,
            }
        )

    _add_metric("Max Skating Speed", speed_max, " mph", ".2f")
    _add_metric("22+ mph Speed Bursts", bursts_22, "", "d")
    _add_metric("20–22 mph Bursts", bursts_20, "", "d")
    _add_metric("Top Shot Speed", top_shot, " mph", ".2f")
    _add_metric("90+ mph Shots", shots_90, "", "d")
    _add_metric("Total Distance Skated", dist_total, " mi", ".1f")

    zone = (
        edge_detail.get("zoneTimeDetails")
        or edge_comparison.get("zoneTimeDetails")
        or {}
    )
    oz_pct = zone.get("offensiveZonePctg")
    nz_pct = zone.get("neutralZonePctg")
    dz_pct = zone.get("defensiveZonePctg")
    zones = None
    if any(v is not None for v in (oz_pct, nz_pct, dz_pct)):
        oz = round(float(oz_pct or 0) * (100 if float(oz_pct or 0) <= 1 else 1), 1)
        nz = round(float(nz_pct or 0) * (100 if float(nz_pct or 0) <= 1 else 1), 1)
        dz = round(float(dz_pct or 0) * (100 if float(dz_pct or 0) <= 1 else 1), 1)
        oz_rank = zone.get("offensiveZoneRank")
        zones = {
            "offensive": oz,
            "neutral": nz,
            "defensive": dz,
            "offensiveRank": int(oz_rank)
            if isinstance(oz_rank, (int, float))
            else None,
            "offensiveLeagueAvg": (
                round(
                    float(zone["offensiveZoneLeagueAvg"])
                    * (100 if float(zone["offensiveZoneLeagueAvg"]) <= 1 else 1),
                    1,
                )
                if zone.get("offensiveZoneLeagueAvg") is not None
                else None
            ),
        }

    sog_list = (
        edge_detail.get("sogSummary")
        or edge_comparison.get("shotLocationSummary")
        or edge_detail.get("shotLocationDetails")
        or []
    )
    shot_locations = []
    for item in sog_list:
        if not isinstance(item, dict):
            continue
        code = str(item.get("locationCode") or item.get("area") or "")
        if not code:
            continue
        label = code.replace("_", " ").replace("-", " ").title()
        shot_locations.append(
            {
                "zone": label,
                "shots": int(item.get("shots") or item.get("sog") or 0),
                "goals": int(item.get("goals") or 0),
                "shootingPct": _fmt_pct(item.get("shootingPctg")),
                "shotsRank": item.get("shotsRank") or item.get("sogRank"),
                "leagueAvgPct": (
                    _fmt_pct(item.get("shootingPctgLeagueAvg"))
                    if item.get("shootingPctgLeagueAvg") is not None
                    else None
                ),
            }
        )

    if not metrics and not zones and not shot_locations:
        return None

    return {
        "metrics": metrics,
        "zones": zones,
        "shotLocations": shot_locations[:6],
    }


def _parse_person_bio(p: dict[str, Any]) -> dict[str, Any]:
    first = (p.get("firstName") or {}).get("default", "")
    last = (p.get("lastName") or {}).get("default", "")
    city = (p.get("birthCity") or {}).get("default", "")
    state = (p.get("birthStateProvince") or {}).get("default", "")
    country = str(p.get("birthCountry") or "")
    birthplace = ", ".join(part for part in (city, state, country) if part)
    return {
        "playerId": p.get("id"),
        "fullName": f"{first} {last}".strip(),
        "sweaterNumber": p.get("sweaterNumber"),
        "position": p.get("positionCode", ""),
        "headshotUrl": p.get("headshot", ""),
        "shootsCatches": p.get("shootsCatches", "—"),
        "height": _fmt_height(p.get("heightInInches")),
        "weight": f"{p['weightInPounds']} lbs" if p.get("weightInPounds") else "—",
        "age": _calc_age(p.get("birthDate")),
        "birthplace": birthplace or "—",
    }


def fetch_team_profile(team_abbrev: str, season: str | None = None) -> dict[str, Any]:
    abbrev = team_abbrev.strip().upper()
    cache_key = f"nhl_team_profile_v2_{abbrev}_{season or 'current'}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    standing_qs = TeamStanding.objects.filter(team_abbrev__iexact=abbrev)
    if season:
        standing_qs = standing_qs.filter(season_id=season)
    standing = standing_qs.order_by("-season_id").first()

    if standing:
        active_season = standing.season_id
    else:
        latest_season = (
            TeamStanding.objects.values_list("season_id", flat=True)
            .distinct()
            .order_by("-season_id")
            .first()
        )
        active_season = season or latest_season or "20262027"

    directory = _get_team_directory()
    dir_entry = directory.get(abbrev)
    if not standing and not dir_entry:
        raise ValueError(f"Team '{abbrev}' not found.")

    team_id = dir_entry["id"] if dir_entry else None
    team_name = (
        standing.team_name
        if standing
        else (dir_entry["fullName"] if dir_entry else abbrev)
    )
    team_common = standing.team_common_name if standing else team_name.split()[-1]
    team_logo = (
        standing.team_logo
        if standing and standing.team_logo
        else f"https://assets.nhle.com/logos/nhl/svg/{abbrev}_dark.svg"
    )

    report_names = (
        "summary",
        "percentages",
        "realtime",
        "powerplay",
        "penaltykill",
        "faceoffpercentages",
        "goalsbyperiod",
        "leadingtrailing",
        "penalties",
    )

    with ThreadPoolExecutor(max_workers=12) as pool:
        report_futures = {
            name: pool.submit(_fetch_league_team_report, name, active_season)
            for name in report_names
        }
        club_stats_future = pool.submit(
            _safe_get_json, f"{NHL_WEB_API_BASE}/v1/club-stats/{abbrev}/now"
        )
        roster_future = pool.submit(
            _safe_get_json, f"{NHL_WEB_API_BASE}/v1/roster/{abbrev}/current"
        )
        schedule_future = pool.submit(
            _safe_get_json, f"{NHL_WEB_API_BASE}/v1/club-schedule-season/{abbrev}/now"
        )
        prospects_future = pool.submit(
            _safe_get_json, f"{NHL_WEB_API_BASE}/v1/prospects/{abbrev}"
        )
        edge_detail_future = (
            pool.submit(
                _safe_get_json, f"{NHL_WEB_API_BASE}/v1/edge/team-detail/{team_id}/now"
            )
            if team_id is not None
            else None
        )
        edge_comp_future = (
            pool.submit(
                _safe_get_json,
                f"{NHL_WEB_API_BASE}/v1/edge/team-comparison/{team_id}/now",
            )
            if team_id is not None
            else None
        )
        mp_future = pool.submit(get_team_moneypuck, abbrev, active_season)

        league_reports = {name: fut.result() for name, fut in report_futures.items()}
        club_stats = club_stats_future.result()
        roster_raw = roster_future.result()
        schedule_raw = schedule_future.result()
        prospects_raw = prospects_future.result()
        edge_detail = edge_detail_future.result() if edge_detail_future else {}
        edge_comp = edge_comp_future.result() if edge_comp_future else {}
        money_puck = mp_future.result()

    mp_backfill = (
        (money_puck.get("situations") or {}).get("5on5", {}).get("backfill", {})
        if money_puck
        else {}
    )

    # Extract this team's row from each league report
    summary_all = league_reports["summary"]
    pct_all = league_reports["percentages"]
    rt_all = league_reports["realtime"]
    pp_all = league_reports["powerplay"]
    pk_all = league_reports["penaltykill"]
    fo_all = league_reports["faceoffpercentages"]
    period_all = league_reports["goalsbyperiod"]
    sit_all = league_reports["leadingtrailing"]
    pen_all = league_reports["penalties"]

    summary = _find_team_row(summary_all, team_id, team_name)
    if team_id is None and summary.get("teamId") is not None:
        team_id = int(summary["teamId"])

    pct = _find_team_row(pct_all, team_id, team_name)
    rt = _find_team_row(rt_all, team_id, team_name)
    pp = _find_team_row(pp_all, team_id, team_name)
    pk = _find_team_row(pk_all, team_id, team_name)
    fo = _find_team_row(fo_all, team_id, team_name)
    period = _find_team_row(period_all, team_id, team_name)
    sit = _find_team_row(sit_all, team_id, team_name)
    pen = _find_team_row(pen_all, team_id, team_name)

    gp = standing.games_played if standing else int(summary.get("gamesPlayed") or 0)
    wins = standing.wins if standing else int(summary.get("wins") or 0)
    losses = standing.losses if standing else int(summary.get("losses") or 0)
    otl = standing.ot_losses if standing else int(summary.get("otLosses") or 0)
    pts = standing.points if standing else int(summary.get("points") or 0)
    point_pct = (
        standing.point_pctg if standing else float(summary.get("pointPct") or 0.0)
    )
    gf = standing.goals_for if standing else int(summary.get("goalsFor") or 0)
    ga = standing.goals_against if standing else int(summary.get("goalsAgainst") or 0)
    diff = standing.goal_differential if standing else (gf - ga)

    gf_pg = summary.get("goalsForPerGame", round(gf / gp, 2) if gp else 0.0)
    ga_pg = summary.get("goalsAgainstPerGame", round(ga / gp, 2) if gp else 0.0)
    diff_pg = round(diff / gp, 2) if gp else 0.0

    league_pts_rank = _league_rank(summary_all, team_id, "points", True)
    gf_rank = _league_rank(summary_all, team_id, "goalsForPerGame", True)
    ga_rank = _league_rank(summary_all, team_id, "goalsAgainstPerGame", False)
    pp_rank = _league_rank(summary_all, team_id, "powerPlayPct", True)
    pk_rank = _league_rank(summary_all, team_id, "penaltyKillPct", True)
    sf_rank = _league_rank(summary_all, team_id, "shotsForPerGame", True)
    sa_rank = _league_rank(summary_all, team_id, "shotsAgainstPerGame", False)
    fo_rank = _league_rank(summary_all, team_id, "faceoffWinPct", True)
    sat_rank = _league_rank(pct_all, team_id, "satPct", True)
    usat_rank = _league_rank(pct_all, team_id, "usatPct", True)
    hits_rank = _league_rank(rt_all, team_id, "hitsPer60", True)
    blocks_rank = _league_rank(rt_all, team_id, "blockedShotsPer60", True)
    pim_rank = _league_rank(pen_all, team_id, "penaltyMinutesPerGame", False)

    # Headline 6 KPIs
    headline_kpis = [
        {"label": "Record", "value": f"{wins}-{losses}-{otl}"},
        {
            "label": "Points",
            "value": str(pts),
            "rank": _ordinal(league_pts_rank),
            "highlight": True,
        },
        {"label": "Point %", "value": _fmt_pct(point_pct)},
        {
            "label": "GF / GP",
            "value": _fmt_num(gf_pg, 2),
            "rank": _ordinal(gf_rank),
        },
        {
            "label": "GA / GP",
            "value": _fmt_num(ga_pg, 2),
            "rank": _ordinal(ga_rank),
        },
        {"label": "Goal Diff", "value": _fmt_num(diff, 0, signed=True)},
    ]

    # Compute PDO if present
    pdo_raw = pct.get("shootingPlusSavePct5v5")
    pdo_str = "—"
    if pdo_raw is not None:
        p_num = float(pdo_raw)
        pdo_str = f"{p_num * 100:.1f}" if p_num <= 2.0 else f"{p_num:.1f}"

    def _or_mp(primary: str, mp_key: str) -> str:
        if primary and primary != "—":
            return primary
        return mp_backfill.get(mp_key) or primary

    # Categorized Stat Panels
    stat_groups = [
        {
            "title": "Offense & Scoring",
            "items": [
                {"label": "Goals For", "value": str(gf), "highlight": True},
                {
                    "label": "GF / Game",
                    "value": _fmt_num(gf_pg, 2),
                    "rank": _ordinal(gf_rank),
                },
                {"label": "Goal Diff / GP", "value": _fmt_num(diff_pg, 2, signed=True)},
                {
                    "label": "Shots For / GP",
                    "value": _fmt_num(summary.get("shotsForPerGame"), 1),
                    "rank": _ordinal(sf_rank),
                },
                {
                    "label": "5v5 Shooting %",
                    "value": _fmt_pct(pct.get("shootingPct5v5")),
                },
                {"label": "5v5 Goals For", "value": str(period.get("evGoalsFor", "—"))},
                {
                    "label": "Regulation Wins",
                    "value": str(summary.get("regulationWins", "—")),
                },
                {"label": "ROW", "value": str(summary.get("regulationAndOtWins", "—"))},
                {
                    "label": "Shootout Wins",
                    "value": str(summary.get("winsInShootout", "—")),
                },
                {
                    "label": "Empty-Net Goals",
                    "value": str(rt.get("emptyNetGoals", "—")),
                },
                {"label": "Missed Shots", "value": str(rt.get("missedShots", "—"))},
                {"label": "Giveaways", "value": str(rt.get("giveaways", "—"))},
            ],
        },
        {
            "title": "Defense & Goaltending",
            "items": [
                {"label": "Goals Against", "value": str(ga)},
                {
                    "label": "GA / Game",
                    "value": _fmt_num(ga_pg, 2),
                    "rank": _ordinal(ga_rank),
                    "highlight": True,
                },
                {
                    "label": "Shots Against / GP",
                    "value": _fmt_num(summary.get("shotsAgainstPerGame"), 1),
                    "rank": _ordinal(sa_rank),
                },
                {"label": "5v5 Save %", "value": _fmt_sv_pct(pct.get("savePct5v5"))},
                {
                    "label": "5v5 Goals Against",
                    "value": str(period.get("evGoalsAgainst", "—")),
                },
                {"label": "Blocked Shots", "value": str(rt.get("blockedShots", "—"))},
                {
                    "label": "Blocks / 60",
                    "value": _fmt_num(rt.get("blockedShotsPer60"), 1),
                    "rank": _ordinal(blocks_rank),
                },
                {"label": "Takeaways", "value": str(rt.get("takeaways", "—"))},
                {
                    "label": "Takeaways / 60",
                    "value": _fmt_num(rt.get("takeawaysPer60"), 1),
                },
                {"label": "Hits", "value": str(rt.get("hits", "—"))},
                {
                    "label": "Hits / 60",
                    "value": _fmt_num(rt.get("hitsPer60"), 1),
                    "rank": _ordinal(hits_rank),
                },
                {
                    "label": "Giveaways / 60",
                    "value": _fmt_num(rt.get("giveawaysPer60"), 1),
                },
            ],
        },
        {
            "title": "Special Teams",
            "items": [
                {
                    "label": "Power Play %",
                    "value": _fmt_pct(summary.get("powerPlayPct")),
                    "rank": _ordinal(pp_rank),
                    "highlight": True,
                },
                {
                    "label": "Net PP %",
                    "value": _fmt_pct(
                        summary.get("powerPlayNetPct", pp.get("powerPlayNetPct"))
                    ),
                },
                {"label": "PP Goals", "value": str(pp.get("powerPlayGoalsFor", "—"))},
                {
                    "label": "PP Opportunities",
                    "value": str(pp.get("ppOpportunities", "—")),
                },
                {
                    "label": "PP Opp / GP",
                    "value": _fmt_num(pp.get("ppOpportunitiesPerGame"), 2),
                },
                {
                    "label": "PP TOI / GP",
                    "value": _fmt_toi(pp.get("ppTimeOnIcePerGame")),
                },
                {
                    "label": "Penalty Kill %",
                    "value": _fmt_pct(summary.get("penaltyKillPct")),
                    "rank": _ordinal(pk_rank),
                    "highlight": True,
                },
                {
                    "label": "Net PK %",
                    "value": _fmt_pct(
                        summary.get("penaltyKillNetPct", pk.get("penaltyKillNetPct"))
                    ),
                },
                {
                    "label": "Times Shorthanded",
                    "value": str(pk.get("timesShorthanded", "—")),
                },
                {
                    "label": "PP Goals Against",
                    "value": str(pk.get("ppGoalsAgainst", "—")),
                },
                {"label": "SH Goals For", "value": str(pk.get("shGoalsFor", "—"))},
                {
                    "label": "SH Goals Against",
                    "value": str(pp.get("shGoalsAgainst", "—")),
                },
            ],
        },
        {
            "title": "5v5 Possession & Shot Control",
            "items": [
                {
                    "label": "Corsi / SAT %",
                    "value": _or_mp(_fmt_pct(pct.get("satPct")), "satPct"),
                    "rank": _ordinal(sat_rank),
                    "highlight": True,
                },
                {
                    "label": "Fenwick / USAT %",
                    "value": _or_mp(_fmt_pct(pct.get("usatPct")), "usatPct"),
                    "rank": _ordinal(usat_rank),
                },
                {
                    "label": "SAT % Close",
                    "value": _or_mp(_fmt_pct(pct.get("satPctClose")), "satPctClose"),
                },
                {"label": "SAT % Tied", "value": _fmt_pct(pct.get("satPctTied"))},
                {"label": "SAT % Leading", "value": _fmt_pct(pct.get("satPctAhead"))},
                {"label": "SAT % Trailing", "value": _fmt_pct(pct.get("satPctBehind"))},
                {
                    "label": "SAT For",
                    "value": _or_mp(str(rt.get("satFor", "—")), "satFor"),
                },
                {
                    "label": "SAT Against",
                    "value": _or_mp(str(rt.get("satAgainst", "—")), "satAgainst"),
                },
                {
                    "label": "PDO (5v5)",
                    "value": _or_mp(pdo_str, "pdo"),
                    "highlight": True,
                },
                {
                    "label": "5v5 Shooting %",
                    "value": _or_mp(_fmt_pct(pct.get("shootingPct5v5")), "shPct5v5"),
                },
                {
                    "label": "5v5 Save %",
                    "value": _or_mp(_fmt_sv_pct(pct.get("savePct5v5")), "svPct5v5"),
                },
                {
                    "label": "Total SAT",
                    "value": _or_mp(str(rt.get("satTotal", "—")), "satTotal"),
                },
            ],
        },
        {
            "title": "Faceoffs & Discipline",
            "items": [
                {
                    "label": "Faceoff Win %",
                    "value": _fmt_pct(
                        summary.get("faceoffWinPct", fo.get("faceoffWinPct"))
                    ),
                    "rank": _ordinal(fo_rank),
                    "highlight": True,
                },
                {"label": "EV Faceoff %", "value": _fmt_pct(fo.get("evFaceoffPct"))},
                {"label": "PP Faceoff %", "value": _fmt_pct(fo.get("ppFaceoffPct"))},
                {"label": "SH Faceoff %", "value": _fmt_pct(fo.get("shFaceoffPct"))},
                {
                    "label": "Offensive Zone FO%",
                    "value": _fmt_pct(fo.get("offensiveZoneFaceoffPct")),
                },
                {
                    "label": "Defensive Zone FO%",
                    "value": _fmt_pct(fo.get("defensiveZoneFaceoffPct")),
                },
                {
                    "label": "Penalty Minutes",
                    "value": str(pen.get("penaltyMinutes", "—")),
                },
                {
                    "label": "PIM / Game",
                    "value": _fmt_num(pen.get("penaltyMinutesPerGame"), 1),
                    "rank": _ordinal(pim_rank),
                },
                {
                    "label": "Penalties Drawn",
                    "value": str(pen.get("penaltiesDrawn", "—")),
                },
                {
                    "label": "Penalties Taken",
                    "value": str(pen.get("penaltiesTaken", "—")),
                },
                {
                    "label": "Net Penalties",
                    "value": _fmt_num(pen.get("netPenalties"), 0, signed=True),
                },
                {
                    "label": "Net Pen / 60",
                    "value": _fmt_num(pen.get("netPenaltiesPer60"), 2, signed=True),
                },
            ],
        },
        {
            "title": "Situational Records",
            "items": [
                {
                    "label": "Scoring First",
                    "value": _fmt_record(
                        sit.get("winsScoringFirst"),
                        sit.get("lossesScoringFirst"),
                        sit.get("otLossesScoringFirst"),
                    ),
                    "highlight": True,
                },
                {
                    "label": "Trailing First",
                    "value": _fmt_record(
                        sit.get("winsTrailingFirst"),
                        sit.get("lossesTrailingFirst"),
                        sit.get("otLossesTrailingFirst"),
                    ),
                },
                {
                    "label": "Leading After 1st",
                    "value": _fmt_record(
                        sit.get("winsLeadPeriod1"),
                        sit.get("lossesLeadPeriod1"),
                        sit.get("otLossesLeadPeriod1"),
                    ),
                },
                {
                    "label": "Trailing After 1st",
                    "value": _fmt_record(
                        sit.get("winsTrailPeriod1"),
                        sit.get("lossesTrailPeriod1"),
                        sit.get("otLossesTrailPeriod1"),
                    ),
                },
                {
                    "label": "Leading After 2nd",
                    "value": _fmt_record(
                        sit.get("winsLeadPeriod2"),
                        sit.get("lossesLeadPeriod2"),
                        sit.get("otLossesLeadPeriod2"),
                    ),
                },
                {
                    "label": "Trailing After 2nd",
                    "value": _fmt_record(
                        sit.get("winsTrailPeriod2"),
                        sit.get("lossesTrailPeriod2"),
                        sit.get("otLossesTrailPeriod2"),
                    ),
                },
            ],
        },
    ]

    # Period-by-period scoring breakdown
    period_scoring = []
    for label, gf_key, ga_key in (
        ("1st Period", "period1GoalsFor", "period1GoalsAgainst"),
        ("2nd Period", "period2GoalsFor", "period2GoalsAgainst"),
        ("3rd Period", "period3GoalsFor", "period3GoalsAgainst"),
        ("Overtime", "otGoalsFor", "otGoalsAgainst"),
    ):
        if period.get(gf_key) is not None or period.get(ga_key) is not None:
            p_gf = int(period.get(gf_key) or 0)
            p_ga = int(period.get(ga_key) or 0)
            period_scoring.append(
                {
                    "period": label,
                    "gf": p_gf,
                    "ga": p_ga,
                    "diff": p_gf - p_ga,
                }
            )

    # Index roster bio metadata by playerId so club-stats tables include sweater #, size, shoots, age
    roster_bio_map: dict[int, dict[str, Any]] = {}
    roster_groups: dict[str, list[dict[str, Any]]] = {
        "forwards": [],
        "defensemen": [],
        "goalies": [],
    }
    for group_key in ("forwards", "defensemen", "goalies"):
        for raw_p in roster_raw.get(group_key) or []:
            parsed = _parse_person_bio(raw_p)
            roster_groups[group_key].append(parsed)
            if parsed["playerId"] is not None:
                roster_bio_map[int(parsed["playerId"])] = parsed

    # Club Skaters & Goalies Stats
    skaters_out = []
    for s in club_stats.get("skaters") or []:
        pid = int(s.get("playerId") or 0)
        bio = roster_bio_map.get(pid, {})
        first = (s.get("firstName") or {}).get("default", "")
        last = (s.get("lastName") or {}).get("default", "")
        raw_spct = float(s.get("shootingPctg") or 0.0)
        spct_disp = round(raw_spct * 100, 1) if raw_spct <= 1.0 else round(raw_spct, 1)

        skaters_out.append(
            {
                "playerId": pid,
                "fullName": f"{first} {last}".strip() or bio.get("fullName", "Unknown"),
                "headshotUrl": s.get("headshot") or bio.get("headshotUrl", ""),
                "sweaterNumber": bio.get("sweaterNumber"),
                "position": s.get("positionCode") or bio.get("position", ""),
                "gp": int(s.get("gamesPlayed") or 0),
                "goals": int(s.get("goals") or 0),
                "assists": int(s.get("assists") or 0),
                "points": int(s.get("points") or 0),
                "plusMinus": int(s.get("plusMinus") or 0),
                "pim": int(s.get("penaltyMinutes") or 0),
                "ppGoals": int(s.get("powerPlayGoals") or 0),
                "shGoals": int(s.get("shorthandedGoals") or 0),
                "gwg": int(s.get("gameWinningGoals") or 0),
                "shots": int(s.get("shots") or 0),
                "shootingPct": spct_disp,
                "toiPerGame": _fmt_toi(s.get("avgTimeOnIcePerGame")),
                "faceoffWinPct": (
                    _fmt_pct(s.get("faceoffWinPctg"))
                    if s.get("faceoffWinPctg") is not None
                    else "—"
                ),
            }
        )
    skaters_out.sort(key=lambda x: (-x["points"], -x["goals"], x["gp"]))

    goalies_out = []
    for g in club_stats.get("goalies") or []:
        pid = int(g.get("playerId") or 0)
        bio = roster_bio_map.get(pid, {})
        first = (g.get("firstName") or {}).get("default", "")
        last = (g.get("lastName") or {}).get("default", "")
        w = int(g.get("wins") or 0)
        l = int(g.get("losses") or 0)
        ot = int(g.get("overtimeLosses") or 0)
        sv = float(g.get("savePercentage") or 0.0)

        goalies_out.append(
            {
                "playerId": pid,
                "fullName": f"{first} {last}".strip() or bio.get("fullName", "Unknown"),
                "headshotUrl": g.get("headshot") or bio.get("headshotUrl", ""),
                "sweaterNumber": bio.get("sweaterNumber"),
                "gp": int(g.get("gamesPlayed") or 0),
                "gs": int(g.get("gamesStarted") or 0),
                "wins": w,
                "losses": l,
                "otLosses": ot,
                "record": f"{w}-{l}-{ot}",
                "savePct": round(sv, 4),
                "savePctDisplay": _fmt_sv_pct(sv),
                "gaa": round(float(g.get("goalsAgainstAverage") or 0.0), 2),
                "shutouts": int(g.get("shutouts") or 0),
                "saves": int(g.get("saves") or 0),
                "shotsAgainst": int(g.get("shotsAgainst") or 0),
            }
        )
    goalies_out.sort(key=lambda x: (-x["gp"], -x["savePct"]))

    # Schedule: Recent 10 Results & Next 10 Upcoming Games
    recent_games = []
    upcoming_games = []
    for gm in schedule_raw.get("games") or []:
        if gm.get("gameType") not in (2, 3):
            continue
        state = str(gm.get("gameState") or "")
        home = gm.get("homeTeam") or {}
        away = gm.get("awayTeam") or {}
        is_home = str(home.get("abbrev") or "").upper() == abbrev
        opp = away if is_home else home
        us = home if is_home else away

        entry = {
            "gameId": gm.get("id"),
            "date": gm.get("gameDate", ""),
            "isHome": is_home,
            "opponentAbbrev": opp.get("abbrev", ""),
            "opponentLogo": opp.get("darkLogo") or opp.get("logo", ""),
            "venue": (gm.get("venue") or {}).get("default", ""),
            "gameState": state,
            "startTimeUTC": gm.get("startTimeUTC", ""),
            "teamScore": us.get("score"),
            "opponentScore": opp.get("score"),
            "periodType": (gm.get("gameOutcome") or {}).get("lastPeriodType", ""),
            "result": "",
        }

        if state in ("FINAL", "OFF"):
            t_score = int(us.get("score") or 0)
            o_score = int(opp.get("score") or 0)
            if t_score > o_score:
                entry["result"] = "W"
            elif entry["periodType"] in ("OT", "SO"):
                entry["result"] = "OTL"
            else:
                entry["result"] = "L"
            recent_games.append(entry)
        else:
            upcoming_games.append(entry)

    recent_games = list(reversed(recent_games))[:10]
    upcoming_games = upcoming_games[:10]

    # Prospects
    prospects = {
        "forwards": [_parse_person_bio(p) for p in prospects_raw.get("forwards") or []],
        "defensemen": [
            _parse_person_bio(p) for p in prospects_raw.get("defensemen") or []
        ],
        "goalies": [_parse_person_bio(p) for p in prospects_raw.get("goalies") or []],
    }

    home_rec = (
        f"{standing.home_wins}-{standing.home_losses}-{standing.home_ot_losses}"
        if standing
        else "—"
    )
    away_rec = (
        f"{standing.road_wins}-{standing.road_losses}-{standing.road_ot_losses}"
        if standing
        else "—"
    )
    l10_rec = (
        f"{standing.l10_wins}-{standing.l10_losses}-{standing.l10_ot_losses}"
        if standing
        else "—"
    )
    streak = (
        f"{standing.streak_code}{standing.streak_count}"
        if standing and standing.streak_code
        else "—"
    )

    profile = {
        "teamAbbrev": abbrev,
        "teamId": team_id,
        "seasonId": active_season,
        "seasonLabel": _fmt_season(active_season),
        "header": {
            "teamName": team_name,
            "teamCommonName": team_common,
            "teamLogo": team_logo,
            "conferenceName": standing.conference_name if standing else "",
            "divisionName": standing.division_name if standing else "",
            "divisionRank": _ordinal(standing.division_sequence) if standing else None,
            "leagueRank": _ordinal(league_pts_rank),
            "homeRecord": home_rec,
            "awayRecord": away_rec,
            "l10": l10_rec,
            "streak": streak,
        },
        "headlineKpis": headline_kpis,
        "statGroups": stat_groups,
        "periodScoring": period_scoring,
        "edge": _parse_team_edge(edge_detail, edge_comp),
        "skaters": skaters_out,
        "goalies": goalies_out,
        "roster": roster_groups,
        "recentGames": recent_games,
        "upcomingGames": upcoming_games,
        "prospects": prospects,
        "moneyPuck": money_puck,
    }

    cache.set(cache_key, profile, CACHE_TTL_SECONDS)
    return profile
