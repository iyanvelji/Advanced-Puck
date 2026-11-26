from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any
import httpx
from django.core.cache import cache
from analytics.models import GoalieStat, SkaterStat, TeamStanding
from analytics.services.moneypuck import get_goalie_moneypuck, get_skater_moneypuck

NHL_WEB_API_BASE = "https://api-web.nhle.com"
NHL_STATS_API_BASE = "https://api.nhle.com/stats/rest/en"
CACHE_TTL_SECONDS = 600


def _fmt_season(season_id: int | str) -> str:
    s = str(season_id or "")
    return f"{s[:4]}–{s[6:]}" if len(s) == 8 else s


def _fmt_toi(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    total = int(round(float(seconds)))
    mins, secs = divmod(total, 60)
    return f"{mins}:{secs:02d}"


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
        with httpx.Client(follow_redirects=True, timeout=12.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
    except (httpx.HTTPError, ValueError):
        pass
    return {}


def _fetch_stats_report(
    role: str, report: str, player_id: int, season_id: str
) -> dict[str, Any]:
    url = f"{NHL_STATS_API_BASE}/{role}/{report}"
    payload = _safe_get_json(
        url,
        params={
            "isAggregate": "false",
            "isGame": "false",
            "cayenneExp": f"playerId={player_id} and seasonId={season_id} and gameTypeId=2",
            "limit": 1,
        },
    )
    rows = payload.get("data", [])
    return rows[0] if rows else {}


def _resolve_active_season(landing: dict[str, Any]) -> str:
    featured = landing.get("featuredStats", {})
    if featured and featured.get("season"):
        return str(featured["season"])

    latest = (
        SkaterStat.objects.values_list("season_id", flat=True)
        .distinct()
        .order_by("-season_id")
        .first()
        or TeamStanding.objects.values_list("season_id", flat=True)
        .distinct()
        .order_by("-season_id")
        .first()
    )
    return latest or "20262027"


def _parse_skater_edge(edge_raw: dict[str, Any]) -> dict[str, Any] | None:
    if not edge_raw:
        return None

    skating_speed = edge_raw.get("skatingSpeed") or {}
    speed_max_obj = skating_speed.get("speedMax") or {}
    bursts_22_obj = skating_speed.get("burstsOver22") or {}
    bursts_20_obj = skating_speed.get("bursts20To22") or {}

    shot_speed = edge_raw.get("topShotSpeed") or edge_raw.get("shotSpeed") or {}
    shot_max_obj = shot_speed.get("topShotSpeed") or shot_speed

    distance = edge_raw.get("skatingDistance") or {}
    total_dist_obj = distance.get("total") or distance

    sog_summary = edge_raw.get("sogSummary") or []
    high_danger = next(
        (
            item
            for item in sog_summary
            if isinstance(item, dict)
            and "high" in str(item.get("locationCode", "")).lower()
        ),
        None,
    )
    mid_range = next(
        (
            item
            for item in sog_summary
            if isinstance(item, dict)
            and "mid" in str(item.get("locationCode", "")).lower()
        ),
        None,
    )
    long_range = next(
        (
            item
            for item in sog_summary
            if isinstance(item, dict)
            and "long" in str(item.get("locationCode", "")).lower()
        ),
        None,
    )

    zone = edge_raw.get("zoneTimeDetails") or {}
    oz_pct = zone.get("offensiveZonePctg")
    nz_pct = zone.get("neutralZonePctg")
    dz_pct = zone.get("defensiveZonePctg")

    metrics: list[dict[str, Any]] = []

    top_speed = _extract_metric_value(speed_max_obj, "imperial")
    if top_speed is not None:
        metrics.append(
            {
                "label": "Max Skating Speed",
                "value": f"{top_speed:.2f} mph",
                "percentile": _normalize_percentile(speed_max_obj.get("percentile")),
                "leagueAvg": (
                    f"{_extract_metric_value(speed_max_obj.get('leagueAvg'), 'imperial'):.2f} mph"
                    if _extract_metric_value(speed_max_obj.get("leagueAvg"), "imperial")
                    is not None
                    else None
                ),
            }
        )

    bursts_22 = _extract_metric_value(bursts_22_obj)
    if bursts_22 is not None:
        metrics.append(
            {
                "label": "22+ mph Speed Bursts",
                "value": str(int(round(bursts_22))),
                "percentile": _normalize_percentile(bursts_22_obj.get("percentile")),
                "leagueAvg": (
                    f"{_extract_metric_value(bursts_22_obj.get('leagueAvg')):.1f}"
                    if _extract_metric_value(bursts_22_obj.get("leagueAvg")) is not None
                    else None
                ),
            }
        )

    bursts_20 = _extract_metric_value(bursts_20_obj)
    if bursts_20 is not None:
        metrics.append(
            {
                "label": "20–22 mph Bursts",
                "value": str(int(round(bursts_20))),
                "percentile": _normalize_percentile(bursts_20_obj.get("percentile")),
                "leagueAvg": None,
            }
        )

    top_shot = _extract_metric_value(shot_max_obj, "imperial")
    if top_shot is not None:
        metrics.append(
            {
                "label": "Top Shot Speed",
                "value": f"{top_shot:.2f} mph",
                "percentile": _normalize_percentile(shot_max_obj.get("percentile")),
                "leagueAvg": (
                    f"{_extract_metric_value(shot_max_obj.get('leagueAvg'), 'imperial'):.2f} mph"
                    if _extract_metric_value(shot_max_obj.get("leagueAvg"), "imperial")
                    is not None
                    else None
                ),
            }
        )

    total_miles = _extract_metric_value(total_dist_obj, "imperial")
    if total_miles is not None:
        metrics.append(
            {
                "label": "Total Distance Skated",
                "value": f"{total_miles:.1f} mi",
                "percentile": _normalize_percentile(total_dist_obj.get("percentile")),
                "leagueAvg": None,
            }
        )

    zones = None
    if any(v is not None for v in (oz_pct, nz_pct, dz_pct)):
        zones = {
            "offensive": round(
                float(oz_pct or 0) * (100 if float(oz_pct or 0) <= 1 else 1), 1
            ),
            "neutral": round(
                float(nz_pct or 0) * (100 if float(nz_pct or 0) <= 1 else 1), 1
            ),
            "defensive": round(
                float(dz_pct or 0) * (100 if float(dz_pct or 0) <= 1 else 1), 1
            ),
            "offensivePercentile": _normalize_percentile(
                zone.get("offensiveZonePercentile")
            ),
        }

    shot_locations = []
    for label, row in (
        ("High-Danger", high_danger),
        ("Mid-Range", mid_range),
        ("Long-Range", long_range),
    ):
        if row:
            shot_locations.append(
                {
                    "zone": label,
                    "shots": row.get("shots", 0),
                    "goals": row.get("goals", 0),
                    "shootingPct": _fmt_pct(row.get("shootingPctg")),
                    "percentile": _normalize_percentile(row.get("shotsPercentile")),
                }
            )

    if not metrics and not zones and not shot_locations:
        return None

    return {
        "metrics": metrics,
        "zones": zones,
        "shotLocations": shot_locations,
    }


def _parse_goalie_edge(edge_raw: dict[str, Any]) -> dict[str, Any] | None:
    if not edge_raw:
        return None

    stats = edge_raw.get("stats") or edge_raw
    metrics: list[dict[str, Any]] = []

    for label, key, formatter in (
        ("Games Above .900", "gamesAbove900", lambda v: str(int(round(v)))),
        ("Pct Games > .900", "pctgGamesAbove900", lambda v: _fmt_pct(v)),
        ("Goal Diff / 60", "goalDifferentialPer60", lambda v: f"{v:+.2f}"),
        ("Avg Goal Support", "goalSupportAvg", lambda v: f"{v:.2f}"),
        ("Point %", "pointPctg", lambda v: _fmt_pct(v)),
    ):
        obj = stats.get(key)
        val = _extract_metric_value(obj)
        if val is not None:
            metrics.append(
                {
                    "label": label,
                    "value": formatter(val),
                    "percentile": (
                        _normalize_percentile(obj.get("percentile"))
                        if isinstance(obj, dict)
                        else None
                    ),
                    "leagueAvg": None,
                }
            )

    shot_locations = []
    for item in edge_raw.get("shotLocationSummary") or []:
        if isinstance(item, dict):
            shot_locations.append(
                {
                    "zone": str(item.get("locationCode", "")).replace("_", " ").title(),
                    "shots": item.get("shotsAgainst", item.get("shots", 0)),
                    "goals": item.get("goalsAgainst", item.get("goals", 0)),
                    "shootingPct": _fmt_sv_pct(item.get("savePctg")),
                    "percentile": _normalize_percentile(item.get("savePctgPercentile")),
                }
            )

    if not metrics and not shot_locations:
        return None

    return {
        "metrics": metrics,
        "zones": None,
        "shotLocations": shot_locations,
    }


def fetch_player_profile(player_id: int) -> dict[str, Any]:
    cache_key = f"nhl_player_profile_v2_{player_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    landing = _safe_get_json(f"{NHL_WEB_API_BASE}/v1/player/{player_id}/landing")
    if not landing:
        raise ValueError(f"Player {player_id} not found in NHL API.")

    position = str(landing.get("position") or "")
    is_goalie = position == "G"
    active_season = _resolve_active_season(landing)

    with ThreadPoolExecutor(max_workers=10) as pool:
        gamelog_future = pool.submit(
            _safe_get_json, f"{NHL_WEB_API_BASE}/v1/player/{player_id}/game-log/now"
        )
        mp_future = pool.submit(
            get_goalie_moneypuck if is_goalie else get_skater_moneypuck,
            player_id,
            active_season,
        )

        if is_goalie:
            edge_future = pool.submit(
                _safe_get_json,
                f"{NHL_WEB_API_BASE}/v1/edge/goalie-detail/{player_id}/now",
            )
            report_futures = {
                name: pool.submit(
                    _fetch_stats_report, "goalie", name, player_id, active_season
                )
                for name in ("summary", "advanced", "savesByStrength")
            }
        else:
            edge_future = pool.submit(
                _safe_get_json,
                f"{NHL_WEB_API_BASE}/v1/edge/skater-detail/{player_id}/now",
            )
            report_futures = {
                name: pool.submit(
                    _fetch_stats_report, "skater", name, player_id, active_season
                )
                for name in (
                    "summary",
                    "realtime",
                    "puckPossessions",
                    "percentages",
                    "timeonice",
                    "powerplay",
                    "penaltykill",
                )
            }

        gamelog_raw = gamelog_future.result()
        edge_raw = edge_future.result()
        reports = {name: fut.result() for name, fut in report_futures.items()}
        money_puck = mp_future.result()

    mp_backfill = (
        (money_puck.get("situations") or {}).get("5on5", {}).get("backfill", {})
        if money_puck
        else {}
    )

    # Core bio
    first_name = (landing.get("firstName") or {}).get("default", "")
    last_name = (landing.get("lastName") or {}).get("default", "")
    full_name = f"{first_name} {last_name}".strip()
    team_abbrev = str(landing.get("currentTeamAbbrev") or "")
    team_name = (landing.get("fullTeamName") or {}).get("default", team_abbrev)

    birth_city = (landing.get("birthCity") or {}).get("default", "")
    birth_state = (landing.get("birthStateProvince") or {}).get("default", "")
    birth_country = str(landing.get("birthCountry") or "")
    birthplace = ", ".join(p for p in (birth_city, birth_state, birth_country) if p)

    draft = landing.get("draftDetails") or {}
    draft_summary = (
        f"{draft.get('year')} · Rd {draft.get('round')}, Pick {draft.get('overallPick')} ({draft.get('teamAbbrev', '')})"
        if draft.get("year")
        else "Undrafted"
    )

    featured_reg = (
        (landing.get("featuredStats") or {}).get("regularSeason") or {}
    ).get("subSeason") or {}
    career_reg = (landing.get("careerTotals") or {}).get("regularSeason") or {}
    career_playoffs = (landing.get("careerTotals") or {}).get("playoffs") or {}

    summary = reports.get("summary") or {}

    # Build rich categorized stat cards for the Season & Advanced tab
    stat_groups: list[dict[str, Any]] = []
    headline_kpis: list[dict[str, Any]] = []

    if is_goalie:
        adv = reports.get("advanced") or {}
        by_str = reports.get("savesByStrength") or {}

        gp = summary.get("gamesPlayed", featured_reg.get("gamesPlayed", 0))
        wins = summary.get("wins", featured_reg.get("wins", 0))
        losses = summary.get("losses", featured_reg.get("losses", 0))
        otl = summary.get("otLosses", featured_reg.get("otLosses", 0))
        sv_pct = summary.get("savePct", featured_reg.get("savePctg"))
        gaa = summary.get("goalsAgainstAverage", featured_reg.get("goalsAgainstAvg"))
        so = summary.get("shutouts", featured_reg.get("shutouts", 0))
        sa = summary.get("shotsAgainst", 0)

        headline_kpis = [
            {"label": "GP", "value": str(gp)},
            {"label": "Record", "value": f"{wins}-{losses}-{otl}"},
            {"label": "SV%", "value": _fmt_sv_pct(sv_pct), "highlight": True},
            {"label": "GAA", "value": f"{float(gaa):.2f}" if gaa is not None else "—"},
            {"label": "Shutouts", "value": str(so)},
            {"label": "Shots Against", "value": str(sa)},
        ]

        stat_groups = [
            {
                "title": "Season Goaltending",
                "items": [
                    {"label": "Games Played", "value": str(gp)},
                    {
                        "label": "Games Started",
                        "value": str(summary.get("gamesStarted", "—")),
                    },
                    {"label": "Wins", "value": str(wins)},
                    {"label": "Losses", "value": str(losses)},
                    {"label": "OT Losses", "value": str(otl)},
                    {
                        "label": "Save %",
                        "value": _fmt_sv_pct(sv_pct),
                        "highlight": True,
                    },
                    {
                        "label": "GAA",
                        "value": f"{float(gaa):.2f}" if gaa is not None else "—",
                    },
                    {"label": "Shutouts", "value": str(so)},
                    {"label": "Saves", "value": str(summary.get("saves", "—"))},
                    {"label": "Shots Against", "value": str(sa)},
                    {
                        "label": "Goals Against",
                        "value": str(summary.get("goalsAgainst", "—")),
                    },
                    {"label": "Total TOI", "value": _fmt_toi(summary.get("timeOnIce"))},
                ],
            },
            {
                "title": "Advanced Quality & Workload",
                "items": [
                    {
                        "label": "Quality Starts",
                        "value": str(adv.get("qualityStart", "—")),
                    },
                    {
                        "label": "Quality Start %",
                        "value": _fmt_pct(adv.get("qualityStartsPct")),
                    },
                    {
                        "label": "Really Bad Starts",
                        "value": str(adv.get("reallyBadStarts", "—")),
                    },
                    {
                        "label": "Complete Games",
                        "value": str(adv.get("completeGames", "—")),
                    },
                    {
                        "label": "Complete Game %",
                        "value": _fmt_pct(adv.get("completeGamePct")),
                    },
                    {
                        "label": "Shots Against / 60",
                        "value": (
                            f"{float(adv['shotsAgainstPer60']):.1f}"
                            if adv.get("shotsAgainstPer60") is not None
                            else "—"
                        ),
                    },
                    {
                        "label": "Goal Support Avg",
                        "value": (
                            f"{float(adv['goalsForAverage']):.2f}"
                            if adv.get("goalsForAverage") is not None
                            else "—"
                        ),
                    },
                    {
                        "label": "Regulation Wins",
                        "value": str(adv.get("regulationWins", "—")),
                    },
                ],
            },
            {
                "title": "Saves by Strength State",
                "items": [
                    {
                        "label": "Even Strength SV%",
                        "value": _fmt_sv_pct(by_str.get("evSavePct")),
                        "highlight": True,
                    },
                    {
                        "label": "EV Shots Against",
                        "value": str(by_str.get("evShotsAgainst", "—")),
                    },
                    {
                        "label": "EV Goals Against",
                        "value": str(by_str.get("evGoalsAgainst", "—")),
                    },
                    {
                        "label": "Power Play SV%",
                        "value": _fmt_sv_pct(by_str.get("ppSavePct")),
                    },
                    {
                        "label": "PP Shots Against",
                        "value": str(by_str.get("ppShotsAgainst", "—")),
                    },
                    {
                        "label": "PP Goals Against",
                        "value": str(by_str.get("ppGoalsAgainst", "—")),
                    },
                    {
                        "label": "Shorthanded SV%",
                        "value": _fmt_sv_pct(by_str.get("shSavePct")),
                    },
                    {
                        "label": "SH Shots Against",
                        "value": str(by_str.get("shShotsAgainst", "—")),
                    },
                ],
            },
        ]
    else:
        rt = reports.get("realtime") or {}
        poss = reports.get("puckPossessions") or {}
        pcts = reports.get("percentages") or {}
        toi = reports.get("timeonice") or {}
        pp = reports.get("powerplay") or {}
        pk = reports.get("penaltykill") or {}

        gp = summary.get("gamesPlayed", featured_reg.get("gamesPlayed", 0))
        goals = summary.get("goals", featured_reg.get("goals", 0))
        assists = summary.get("assists", featured_reg.get("assists", 0))
        points = summary.get("points", featured_reg.get("points", 0))
        pm = summary.get("plusMinus", featured_reg.get("plusMinus", 0))
        toi_pg = _fmt_toi(summary.get("timeOnIcePerGame"))

        headline_kpis = [
            {"label": "GP", "value": str(gp)},
            {"label": "Goals", "value": str(goals)},
            {"label": "Assists", "value": str(assists)},
            {"label": "Points", "value": str(points), "highlight": True},
            {"label": "+/-", "value": f"+{pm}" if int(pm or 0) > 0 else str(pm or 0)},
            {"label": "TOI / GP", "value": toi_pg},
        ]

        on_ice_sh = pcts.get("skaterShootingPct5v5", poss.get("onIceShootingPct"))
        on_ice_sv = pcts.get("skaterSavePct5v5")
        pdo_val = None
        if on_ice_sh is not None and on_ice_sv is not None:
            sh_n = float(on_ice_sh) * (100 if float(on_ice_sh) <= 1 else 1)
            sv_n = float(on_ice_sv) * (100 if float(on_ice_sv) <= 1 else 1)
            pdo_val = f"{sh_n + sv_n:.1f}"

        def _or_mp(primary: str, mp_key: str) -> str:
            if primary and primary not in ("—", "— / —"):
                return primary
            return mp_backfill.get(mp_key) or primary

        stat_groups = [
            {
                "title": "Scoring & Shooting",
                "items": [
                    {"label": "Points", "value": str(points), "highlight": True},
                    {"label": "Goals", "value": str(goals)},
                    {"label": "Assists", "value": str(assists)},
                    {
                        "label": "Points / GP",
                        "value": f"{float(summary.get('pointsPerGame') or 0):.2f}",
                    },
                    {
                        "label": "Even-Strength Goals",
                        "value": str(summary.get("evGoals", "—")),
                    },
                    {
                        "label": "Even-Strength Points",
                        "value": str(summary.get("evPoints", "—")),
                    },
                    {
                        "label": "Shots on Goal",
                        "value": str(
                            summary.get("shots", featured_reg.get("shots", "—"))
                        ),
                    },
                    {
                        "label": "Shooting %",
                        "value": _fmt_pct(
                            summary.get("shootingPct", featured_reg.get("shootingPctg"))
                        ),
                    },
                    {
                        "label": "Game-Winning Goals",
                        "value": str(
                            summary.get(
                                "gameWinningGoals",
                                featured_reg.get("gameWinningGoals", "—"),
                            )
                        ),
                    },
                    {
                        "label": "Overtime Goals",
                        "value": str(
                            summary.get("otGoals", featured_reg.get("otGoals", "—"))
                        ),
                    },
                    {"label": "First Goals", "value": str(rt.get("firstGoals", "—"))},
                    {
                        "label": "Empty-Net Points",
                        "value": str(rt.get("emptyNetPoints", "—")),
                    },
                ],
            },
            {
                "title": "Special Teams & Ice Time",
                "items": [
                    {
                        "label": "PP Points",
                        "value": str(
                            summary.get(
                                "ppPoints", featured_reg.get("powerPlayPoints", "—")
                            )
                        ),
                        "highlight": True,
                    },
                    {
                        "label": "PP Goals",
                        "value": str(
                            summary.get(
                                "ppGoals", featured_reg.get("powerPlayGoals", "—")
                            )
                        ),
                    },
                    {
                        "label": "PP Primary Assists",
                        "value": str(pp.get("ppPrimaryAssists", "—")),
                    },
                    {
                        "label": "PP Points / 60",
                        "value": f"{float(pp['ppPointsPer60']):.2f}"
                        if pp.get("ppPointsPer60") is not None
                        else "—",
                    },
                    {
                        "label": "SH Points",
                        "value": str(
                            summary.get(
                                "shPoints", featured_reg.get("shorthandedPoints", "—")
                            )
                        ),
                    },
                    {
                        "label": "SH Goals",
                        "value": str(
                            summary.get(
                                "shGoals", featured_reg.get("shorthandedGoals", "—")
                            )
                        ),
                    },
                    {"label": "Total TOI / GP", "value": toi_pg},
                    {
                        "label": "Even-Strength TOI / GP",
                        "value": _fmt_toi(toi.get("evTimeOnIcePerGame")),
                    },
                    {
                        "label": "Power Play TOI / GP",
                        "value": _fmt_toi(toi.get("ppTimeOnIcePerGame")),
                    },
                    {
                        "label": "Penalty Kill TOI / GP",
                        "value": _fmt_toi(toi.get("shTimeOnIcePerGame")),
                    },
                    {
                        "label": "Shifts / GP",
                        "value": f"{float(toi['shiftsPerGame']):.1f}"
                        if toi.get("shiftsPerGame") is not None
                        else "—",
                    },
                    {
                        "label": "Avg Shift Length",
                        "value": _fmt_toi(toi.get("timeOnIcePerShift")),
                    },
                ],
            },
            {
                "title": "Possession & On-Ice Analytics (5v5)",
                "items": [
                    {
                        "label": "Corsi / SAT %",
                        "value": _or_mp(
                            _fmt_pct(poss.get("satPct", pcts.get("satPct5v5"))),
                            "satPct",
                        ),
                        "highlight": True,
                    },
                    {
                        "label": "SAT Relative %",
                        "value": _or_mp(
                            f"{float(poss['satRelative']):+.1f}%"
                            if poss.get("satRelative") is not None
                            else "—",
                            "satRel",
                        ),
                    },
                    {
                        "label": "Fenwick / USAT %",
                        "value": _or_mp(
                            _fmt_pct(poss.get("usatPct", pcts.get("usatPct5v5"))),
                            "usatPct",
                        ),
                    },
                    {
                        "label": "USAT Relative %",
                        "value": _or_mp(
                            f"{float(poss['usatRelative']):+.1f}%"
                            if poss.get("usatRelative") is not None
                            else "—",
                            "usatRel",
                        ),
                    },
                    {
                        "label": "SAT For / Against",
                        "value": _or_mp(
                            f"{poss.get('satFor', '—')} / {poss.get('satAgainst', '—')}",
                            "satForAgainst",
                        ),
                    },
                    {
                        "label": "SAT % Close",
                        "value": _or_mp(
                            _fmt_pct(poss.get("satPctClose")),
                            "satPctClose",
                        ),
                    },
                    {
                        "label": "Offensive Zone Start %",
                        "value": _or_mp(
                            _fmt_pct(
                                poss.get("zoneStartPct", pcts.get("zoneStartPct5v5"))
                            ),
                            "ozStartPct",
                        ),
                    },
                    {
                        "label": "On-Ice Shooting %",
                        "value": _or_mp(_fmt_pct(on_ice_sh), "onIceShPct"),
                    },
                    {
                        "label": "On-Ice Save %",
                        "value": _or_mp(_fmt_pct(on_ice_sv), "onIceSvPct"),
                    },
                    {
                        "label": "PDO (5v5)",
                        "value": _or_mp(pdo_val or "—", "pdo"),
                    },
                ],
            },
            {
                "title": "Physical, Micro-Stats & Discipline",
                "items": [
                    {"label": "Hits", "value": str(rt.get("hits", "—"))},
                    {
                        "label": "Hits / 60",
                        "value": f"{float(rt['hitsPer60']):.2f}"
                        if rt.get("hitsPer60") is not None
                        else "—",
                    },
                    {
                        "label": "Blocked Shots",
                        "value": str(rt.get("blockedShots", "—")),
                    },
                    {
                        "label": "Blocks / 60",
                        "value": f"{float(rt['blockedShotsPer60']):.2f}"
                        if rt.get("blockedShotsPer60") is not None
                        else "—",
                    },
                    {"label": "Takeaways", "value": str(rt.get("takeaways", "—"))},
                    {"label": "Giveaways", "value": str(rt.get("giveaways", "—"))},
                    {"label": "Missed Shots", "value": str(rt.get("missedShots", "—"))},
                    {
                        "label": "Posts / Crossbars",
                        "value": str(
                            int(rt.get("missedShotGoalpost") or 0)
                            + int(rt.get("missedShotCrossbar") or 0)
                        ),
                    },
                    {
                        "label": "Faceoff Win %",
                        "value": _fmt_pct(summary.get("faceoffWinPct")),
                    },
                    {
                        "label": "Penalty Minutes",
                        "value": str(
                            summary.get("penaltyMinutes", featured_reg.get("pim", "—"))
                        ),
                    },
                ],
            },
        ]

    # Game log normalization (most recent first)
    game_log = []
    for g in gamelog_raw.get("gameLog") or landing.get("last5Games") or []:
        game_log.append(
            {
                "gameId": g.get("gameId"),
                "date": g.get("gameDate", ""),
                "opponent": g.get("opponentAbbrev", ""),
                "homeRoad": g.get("homeRoadFlag", ""),
                "goals": g.get("goals", 0),
                "assists": g.get("assists", 0),
                "points": g.get("points", 0),
                "plusMinus": g.get("plusMinus", 0),
                "shots": g.get("shots", 0),
                "pim": g.get("pim", 0),
                "ppGoals": g.get("powerPlayGoals", 0),
                "ppPoints": g.get("powerPlayPoints", 0),
                "toi": g.get("toi", "—"),
                # Goalie fields
                "decision": g.get("decision", ""),
                "shotsAgainst": g.get("shotsAgainst"),
                "goalsAgainst": g.get("goalsAgainst"),
                "savePct": _fmt_sv_pct(g.get("savePctg"))
                if g.get("savePctg") is not None
                else "—",
                "shutouts": g.get("shutouts", 0),
            }
        )

    # Career season-by-season table (reverse chronological)
    season_totals = []
    for st in reversed(landing.get("seasonTotals") or []):
        season_totals.append(
            {
                "season": _fmt_season(st.get("season", "")),
                "league": st.get("leagueAbbrev", ""),
                "team": (st.get("teamName") or {}).get("default", ""),
                "gameType": "Playoffs" if st.get("gameTypeId") == 3 else "Regular",
                "gp": st.get("gamesPlayed", 0),
                "goals": st.get("goals", 0),
                "assists": st.get("assists", 0),
                "points": st.get("points", 0),
                "plusMinus": st.get("plusMinus"),
                "pim": st.get("pim", 0),
                "shots": st.get("shots"),
                "ppGoals": st.get("powerPlayGoals"),
                "gwg": st.get("gameWinningGoals"),
                "avgToi": st.get("avgToi", "—"),
                # Goalie fields
                "wins": st.get("wins"),
                "losses": st.get("losses"),
                "otLosses": st.get("otLosses"),
                "gaa": round(float(st["goalsAgainstAvg"]), 2)
                if st.get("goalsAgainstAvg") is not None
                else None,
                "savePct": _fmt_sv_pct(st.get("savePctg"))
                if st.get("savePctg") is not None
                else "—",
                "shutouts": st.get("shutouts"),
            }
        )

    # Awards
    awards = []
    for aw in landing.get("awards") or []:
        trophy = (aw.get("trophy") or {}).get("default", "")
        seasons = [
            _fmt_season(s.get("seasonId", ""))
            for s in (aw.get("seasons") or [])
            if s.get("seasonId")
        ]
        if trophy:
            awards.append({"trophy": trophy, "seasons": seasons, "count": len(seasons)})

    profile = {
        "playerId": player_id,
        "seasonId": active_season,
        "seasonLabel": _fmt_season(active_season),
        "isGoalie": is_goalie,
        "bio": {
            "fullName": full_name,
            "sweaterNumber": landing.get("sweaterNumber"),
            "position": position,
            "teamAbbrev": team_abbrev,
            "teamName": team_name,
            "teamLogo": landing.get("teamLogo", ""),
            "headshotUrl": landing.get("headshot", ""),
            "heroImageUrl": landing.get("heroImage", ""),
            "height": _fmt_height(landing.get("heightInInches")),
            "weight": f"{landing['weightInPounds']} lbs"
            if landing.get("weightInPounds")
            else "—",
            "shootsCatches": landing.get("shootsCatches", "—"),
            "birthDate": landing.get("birthDate", "—"),
            "age": _calc_age(landing.get("birthDate")),
            "birthplace": birthplace or "—",
            "draft": draft_summary,
            "isActive": bool(landing.get("isActive", True)),
            "inHHOF": bool(landing.get("inHHOF", False)),
        },
        "headlineKpis": headline_kpis,
        "statGroups": stat_groups,
        "edge": _parse_goalie_edge(edge_raw)
        if is_goalie
        else _parse_skater_edge(edge_raw),
        "gameLog": game_log,
        "careerTotals": {
            "regularSeason": career_reg,
            "playoffs": career_playoffs,
        },
        "seasonTotals": season_totals,
        "awards": awards,
        "moneyPuck": money_puck,
    }

    cache.set(cache_key, profile, CACHE_TTL_SECONDS)
    return profile
