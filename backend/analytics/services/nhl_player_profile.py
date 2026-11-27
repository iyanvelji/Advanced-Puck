from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any
import httpx
from django.core.cache import cache
from analytics.models import GoalieStat, SkaterStat, TeamStanding
from analytics.services.moneypuck import (
    get_goalie_moneypuck,
    get_skater_league_distributions,
    get_skater_moneypuck,
)

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


def _fetch_league_report(
    role: str, report: str, season_id: str
) -> list[dict[str, Any]]:
    """Fetch and cache (1 hr) all regular-season league rows for a player report."""
    key = f"nhl_league_rep_v1_{season_id}_{role}_{report}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    rows: list[dict[str, Any]] = []
    start = 0
    url = f"{NHL_STATS_API_BASE}/{role}/{report}"
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            while True:
                resp = client.get(
                    url,
                    params={
                        "isAggregate": "false",
                        "isGame": "false",
                        "cayenneExp": f"seasonId={season_id} and gameTypeId=2",
                        "start": start,
                        "limit": 100,
                    },
                )
                if resp.status_code != 200:
                    break
                payload = resp.json()
                batch = payload.get("data") or []
                total = int(payload.get("total") or 0)
                if not batch:
                    break
                rows.extend(batch)
                start += len(batch)
                if (total and start >= total) or len(batch) < 100:
                    break
    except (httpx.HTTPError, ValueError):
        pass

    if rows:
        cache.set(key, rows, 3600)
    return rows


def _pctile_str(
    val: float | int | None, pop: list[float], higher_is_better: bool = True
) -> str | None:
    if val is None or not pop:
        return None
    v = float(val)
    if higher_is_better:
        below = sum(1 for x in pop if x < v)
        equal = sum(1 for x in pop if x == v)
    else:
        below = sum(1 for x in pop if x > v)
        equal = sum(1 for x in pop if x == v)
    pct = max(1, min(99, int(round(((below + 0.5 * equal) / len(pop)) * 100.0))))
    return f"{pct}%ile"


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
    cache_key = f"nhl_player_profile_v3_{player_id}"
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
            league_futures = {
                name: pool.submit(_fetch_league_report, "goalie", name, active_season)
                for name in ("summary", "advanced", "savesByStrength")
            }
            mp_dists_future = None
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
            league_futures = {
                name: pool.submit(_fetch_league_report, "skater", name, active_season)
                for name in ("summary", "realtime")
            }
            mp_dists_future = pool.submit(
                get_skater_league_distributions, active_season
            )

        gamelog_raw = gamelog_future.result()
        edge_raw = edge_future.result()
        reports = {name: fut.result() for name, fut in report_futures.items()}
        money_puck = mp_future.result()
        league_reports = {name: fut.result() for name, fut in league_futures.items()}
        mp_dists = mp_dists_future.result() if mp_dists_future else {}

    mp_sits = (money_puck.get("situations") or {}) if money_puck else {}

    mp_s5_bf = mp_sits.get("5on5", {}).get("backfill", {})
    mp_s5_rk = mp_sits.get("5on5", {}).get("backfillRanks", {})
    mp_all_bf = mp_sits.get("all", {}).get("backfill", {})
    mp_pp_bf = mp_sits.get("5on4", {}).get("backfill", {})
    mp_pk_bf = mp_sits.get("4on5", {}).get("backfill", {})

    def _box(
        label: str,
        value: str,
        rank: str | None = None,
        highlight: bool = False,
    ) -> dict[str, Any]:
        d: dict[str, Any] = {"label": label, "value": value, "rank": rank}
        if highlight:
            d["highlight"] = True
        return d

    def _nhl_pct(
        val: float | int | None,
        rep_name: str,
        field: str,
        higher: bool = True,
        min_gp: int = 0,
        min_shots: int = 0,
    ) -> str | None:
        if val is None:
            return None
        rows = league_reports.get(rep_name) or []
        pop = [
            float(r[field])
            for r in rows
            if r.get(field) is not None
            and (r.get("gamesPlayed") or 0) >= min_gp
            and (r.get("shots") or 0) >= min_shots
        ]
        if len(pop) < 10:
            pop = [float(r[field]) for r in rows if r.get(field) is not None]
        return _pctile_str(val, pop, higher)

    def _dist_pct(
        val: float | int | None, dist_key: str, higher: bool = True
    ) -> str | None:
        return _pctile_str(val, mp_dists.get(dist_key) or [], higher)

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

        gl_win_pct = (wins / gp) if gp else None
        gl_win_pop = [
            float(r["wins"]) / float(r["gamesPlayed"])
            for r in (league_reports.get("summary") or [])
            if (r.get("gamesPlayed") or 0) >= 3 and r.get("wins") is not None
        ]

        def _g_or_mp(primary: str, mp_d: dict[str, Any], key: str) -> str:
            return (
                primary if (primary and primary != "—") else (mp_d.get(key) or primary)
            )

        headline_kpis = [
            _box("GP", str(gp), _nhl_pct(gp, "summary", "gamesPlayed")),
            _box(
                "Record", f"{wins}-{losses}-{otl}", _pctile_str(gl_win_pct, gl_win_pop)
            ),
            _box(
                "SV%",
                _fmt_sv_pct(sv_pct),
                _nhl_pct(sv_pct, "summary", "savePct", True, min_gp=3),
                True,
            ),
            _box(
                "GAA",
                f"{float(gaa):.2f}" if gaa is not None else "—",
                _nhl_pct(gaa, "summary", "goalsAgainstAverage", False, min_gp=3),
            ),
            _box("Shutouts", str(so), _nhl_pct(so, "summary", "shutouts")),
            _box("Shots Against", str(sa), _nhl_pct(sa, "summary", "shotsAgainst")),
        ]

        toi_val = (
            summary.get("timeOnIce")
            if summary.get("timeOnIce") is not None
            else mp_all_bf.get("timeOnIce")
        )
        ev_sv_str = _g_or_mp(_fmt_sv_pct(by_str.get("evSavePct")), mp_s5_bf, "savePct")
        pp_sv_str = _g_or_mp(_fmt_sv_pct(by_str.get("ppSavePct")), mp_pk_bf, "savePct")
        sh_sv_str = _g_or_mp(_fmt_sv_pct(by_str.get("shSavePct")), mp_pp_bf, "savePct")

        stat_groups = [
            {
                "title": "Season Goaltending",
                "items": [
                    _box(
                        "Games Played", str(gp), _nhl_pct(gp, "summary", "gamesPlayed")
                    ),
                    _box(
                        "Games Started",
                        str(summary.get("gamesStarted", "—")),
                        _nhl_pct(
                            summary.get("gamesStarted"), "summary", "gamesStarted"
                        ),
                    ),
                    _box("Wins", str(wins), _nhl_pct(wins, "summary", "wins")),
                    _box(
                        "Losses",
                        str(losses),
                        _nhl_pct(losses, "summary", "losses", False),
                    ),
                    _box(
                        "OT Losses",
                        str(otl),
                        _nhl_pct(otl, "summary", "otLosses", False),
                    ),
                    _box(
                        "Save %",
                        _fmt_sv_pct(sv_pct),
                        _nhl_pct(sv_pct, "summary", "savePct", True, min_gp=3),
                        True,
                    ),
                    _box(
                        "GAA",
                        f"{float(gaa):.2f}" if gaa is not None else "—",
                        _nhl_pct(
                            gaa, "summary", "goalsAgainstAverage", False, min_gp=3
                        ),
                    ),
                    _box("Shutouts", str(so), _nhl_pct(so, "summary", "shutouts")),
                    _box(
                        "Saves",
                        str(summary.get("saves", "—")),
                        _nhl_pct(summary.get("saves"), "summary", "saves"),
                    ),
                    _box(
                        "Shots Against",
                        str(sa),
                        _nhl_pct(sa, "summary", "shotsAgainst"),
                    ),
                    _box(
                        "Goals Against",
                        str(summary.get("goalsAgainst", "—")),
                        _nhl_pct(
                            summary.get("goalsAgainst"),
                            "summary",
                            "goalsAgainst",
                            False,
                        ),
                    ),
                    _box(
                        "Total TOI",
                        _fmt_toi(toi_val),
                        _nhl_pct(summary.get("timeOnIce"), "summary", "timeOnIce")
                        or mp_sits.get("all", {})
                        .get("backfillRanks", {})
                        .get("timeOnIce"),
                    ),
                ],
            },
            {
                "title": "Advanced Quality & Workload",
                "items": [
                    _box(
                        "Quality Starts",
                        str(adv.get("qualityStart", "—")),
                        _nhl_pct(adv.get("qualityStart"), "advanced", "qualityStart"),
                    ),
                    _box(
                        "Quality Start %",
                        _fmt_pct(adv.get("qualityStartsPct")),
                        _nhl_pct(
                            adv.get("qualityStartsPct"),
                            "advanced",
                            "qualityStartsPct",
                            True,
                            min_gp=3,
                        ),
                    ),
                    _box(
                        "Really Bad Starts",
                        str(adv.get("reallyBadStarts", "—")),
                        _nhl_pct(
                            adv.get("reallyBadStarts"),
                            "advanced",
                            "reallyBadStarts",
                            False,
                        ),
                    ),
                    _box(
                        "Complete Games",
                        str(adv.get("completeGames", "—")),
                        _nhl_pct(adv.get("completeGames"), "advanced", "completeGames"),
                    ),
                    _box(
                        "Complete Game %",
                        _fmt_pct(adv.get("completeGamePct")),
                        _nhl_pct(
                            adv.get("completeGamePct"),
                            "advanced",
                            "completeGamePct",
                            True,
                            min_gp=3,
                        ),
                    ),
                    _box(
                        "Shots Against / 60",
                        f"{float(adv['shotsAgainstPer60']):.1f}"
                        if adv.get("shotsAgainstPer60") is not None
                        else "—",
                        _nhl_pct(
                            adv.get("shotsAgainstPer60"),
                            "advanced",
                            "shotsAgainstPer60",
                            False,
                            min_gp=3,
                        ),
                    ),
                    _box(
                        "Goal Support Avg",
                        f"{float(adv['goalsForAverage']):.2f}"
                        if adv.get("goalsForAverage") is not None
                        else "—",
                        _nhl_pct(
                            adv.get("goalsForAverage"),
                            "advanced",
                            "goalsForAverage",
                            True,
                            min_gp=3,
                        ),
                    ),
                    _box(
                        "Regulation Wins",
                        str(adv.get("regulationWins", "—")),
                        _nhl_pct(
                            adv.get("regulationWins"), "advanced", "regulationWins"
                        ),
                    ),
                ],
            },
            {
                "title": "Saves by Strength State",
                "items": [
                    _box(
                        "Even Strength SV%",
                        ev_sv_str,
                        _nhl_pct(
                            by_str.get("evSavePct"),
                            "savesByStrength",
                            "evSavePct",
                            True,
                            min_gp=3,
                        )
                        or mp_s5_rk.get("savePct"),
                        True,
                    ),
                    _box(
                        "EV Shots Against",
                        _g_or_mp(
                            str(by_str.get("evShotsAgainst", "—")),
                            mp_s5_bf,
                            "shotsAgainst",
                        ),
                        _nhl_pct(
                            by_str.get("evShotsAgainst"),
                            "savesByStrength",
                            "evShotsAgainst",
                        )
                        or mp_s5_rk.get("shotsAgainst"),
                    ),
                    _box(
                        "EV Goals Against",
                        _g_or_mp(
                            str(by_str.get("evGoalsAgainst", "—")),
                            mp_s5_bf,
                            "goalsAgainst",
                        ),
                        _nhl_pct(
                            by_str.get("evGoalsAgainst"),
                            "savesByStrength",
                            "evGoalsAgainst",
                            False,
                        )
                        or mp_s5_rk.get("goalsAgainst"),
                    ),
                    _box(
                        "Power Play SV%",
                        pp_sv_str,
                        _nhl_pct(
                            by_str.get("ppSavePct"),
                            "savesByStrength",
                            "ppSavePct",
                            True,
                            min_gp=3,
                        )
                        or mp_sits.get("4on5", {})
                        .get("backfillRanks", {})
                        .get("savePct"),
                    ),
                    _box(
                        "PP Shots Against",
                        _g_or_mp(
                            str(by_str.get("ppShotsAgainst", "—")),
                            mp_pk_bf,
                            "shotsAgainst",
                        ),
                        _nhl_pct(
                            by_str.get("ppShotsAgainst"),
                            "savesByStrength",
                            "ppShotsAgainst",
                        )
                        or mp_sits.get("4on5", {})
                        .get("backfillRanks", {})
                        .get("shotsAgainst"),
                    ),
                    _box(
                        "PP Goals Against",
                        _g_or_mp(
                            str(by_str.get("ppGoalsAgainst", "—")),
                            mp_pk_bf,
                            "goalsAgainst",
                        ),
                        _nhl_pct(
                            by_str.get("ppGoalsAgainst"),
                            "savesByStrength",
                            "ppGoalsAgainst",
                            False,
                        )
                        or mp_sits.get("4on5", {})
                        .get("backfillRanks", {})
                        .get("goalsAgainst"),
                    ),
                    _box(
                        "Shorthanded SV%",
                        sh_sv_str,
                        _nhl_pct(
                            by_str.get("shSavePct"),
                            "savesByStrength",
                            "shSavePct",
                            True,
                            min_gp=3,
                        )
                        or mp_sits.get("5on4", {})
                        .get("backfillRanks", {})
                        .get("savePct"),
                    ),
                    _box(
                        "SH Shots Against",
                        _g_or_mp(
                            str(by_str.get("shShotsAgainst", "—")),
                            mp_pp_bf,
                            "shotsAgainst",
                        ),
                        _nhl_pct(
                            by_str.get("shShotsAgainst"),
                            "savesByStrength",
                            "shShotsAgainst",
                        )
                        or mp_sits.get("5on4", {})
                        .get("backfillRanks", {})
                        .get("shotsAgainst"),
                    ),
                ],
            },
        ]
    else:
        rt = reports.get("realtime") or {}
        poss = reports.get("puckPossessions") or {}
        pcts = reports.get("percentages") or {}
        toi = reports.get("timeonice") or {}
        pp = reports.get("powerplay") or {}

        gp = summary.get("gamesPlayed", featured_reg.get("gamesPlayed", 0))
        goals = summary.get("goals", featured_reg.get("goals", 0))
        assists = summary.get("assists", featured_reg.get("assists", 0))
        points = summary.get("points", featured_reg.get("points", 0))
        pm = summary.get("plusMinus", featured_reg.get("plusMinus", 0))

        toi_sec = summary.get("timeOnIcePerGame")
        if toi_sec is None:
            toi_sec = mp_all_bf.get("toiPerGame")
        toi_pg = _fmt_toi(toi_sec)

        headline_kpis = [
            _box("GP", str(gp), _nhl_pct(gp, "summary", "gamesPlayed")),
            _box("Goals", str(goals), _nhl_pct(goals, "summary", "goals")),
            _box("Assists", str(assists), _nhl_pct(assists, "summary", "assists")),
            _box("Points", str(points), _nhl_pct(points, "summary", "points"), True),
            _box(
                "+/-",
                f"+{pm}" if int(pm or 0) > 0 else str(pm or 0),
                _nhl_pct(pm, "summary", "plusMinus"),
            ),
            _box("TOI / GP", toi_pg, _nhl_pct(toi_sec, "summary", "timeOnIcePerGame")),
        ]

        on_ice_sh = pcts.get("skaterShootingPct5v5", poss.get("onIceShootingPct"))
        on_ice_sv = pcts.get("skaterSavePct5v5")
        pdo_val = None
        if on_ice_sh is not None and on_ice_sv is not None:
            sh_n = float(on_ice_sh) * (100 if float(on_ice_sh) <= 1 else 1)
            sv_n = float(on_ice_sv) * (100 if float(on_ice_sv) <= 1 else 1)
            pdo_val = f"{sh_n + sv_n:.1f}"

        def _or_mp(primary: str, mp_key: str, src: dict[str, Any] = mp_s5_bf) -> str:
            if primary and primary not in ("—", "— / —"):
                return primary
            val = src.get(mp_key)
            return str(val) if val is not None else primary

        def _num_or_mp(raw: Any, src: dict[str, Any], mp_key: str) -> float | None:
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass
            fb = src.get(mp_key)
            if fb is None:
                return None
            try:
                return float(str(fb).replace("%", "").replace("+", ""))
            except (TypeError, ValueError):
                return None

        posts_val = int(rt.get("missedShotGoalpost") or 0) + int(
            rt.get("missedShotCrossbar") or 0
        )
        posts_pop = [
            float(
                (r.get("missedShotGoalpost") or 0) + (r.get("missedShotCrossbar") or 0)
            )
            for r in (league_reports.get("realtime") or [])
        ]

        sog_val = summary.get("shots", featured_reg.get("shots"))
        sh_pct_val = summary.get("shootingPct", featured_reg.get("shootingPctg"))
        gwg_val = summary.get("gameWinningGoals", featured_reg.get("gameWinningGoals"))
        otg_val = summary.get("otGoals", featured_reg.get("otGoals"))
        pp_pts_val = summary.get("ppPoints", featured_reg.get("powerPlayPoints"))
        pp_g_val = summary.get("ppGoals", featured_reg.get("powerPlayGoals"))
        sh_pts_val = summary.get("shPoints", featured_reg.get("shorthandedPoints"))
        sh_g_val = summary.get("shGoals", featured_reg.get("shorthandedGoals"))
        pim_val = summary.get("penaltyMinutes", featured_reg.get("pim"))

        ev_toi_sec = (
            toi.get("evTimeOnIcePerGame")
            if toi.get("evTimeOnIcePerGame") is not None
            else mp_s5_bf.get("toiPerGame")
        )
        pp_toi_sec = (
            toi.get("ppTimeOnIcePerGame")
            if toi.get("ppTimeOnIcePerGame") is not None
            else mp_pp_bf.get("toiPerGame")
        )
        pk_toi_sec = (
            toi.get("shTimeOnIcePerGame")
            if toi.get("shTimeOnIcePerGame") is not None
            else mp_pk_bf.get("toiPerGame")
        )
        avg_shift_sec = (
            toi.get("timeOnIcePerShift")
            if toi.get("timeOnIcePerShift") is not None
            else mp_all_bf.get("avgShiftLen")
        )

        stat_groups = [
            {
                "title": "Scoring & Shooting",
                "items": [
                    _box(
                        "Points",
                        str(points),
                        _nhl_pct(points, "summary", "points"),
                        True,
                    ),
                    _box("Goals", str(goals), _nhl_pct(goals, "summary", "goals")),
                    _box(
                        "Assists", str(assists), _nhl_pct(assists, "summary", "assists")
                    ),
                    _box(
                        "Points / GP",
                        f"{float(summary.get('pointsPerGame') or 0):.2f}",
                        _nhl_pct(
                            summary.get("pointsPerGame"),
                            "summary",
                            "pointsPerGame",
                            True,
                            min_gp=5,
                        ),
                    ),
                    _box(
                        "Even-Strength Goals",
                        _or_mp(str(summary.get("evGoals", "—")), "goals", mp_s5_bf),
                        _nhl_pct(summary.get("evGoals"), "summary", "evGoals")
                        or _dist_pct(
                            _num_or_mp(summary.get("evGoals"), mp_s5_bf, "goals"),
                            "evGoals",
                        ),
                    ),
                    _box(
                        "Even-Strength Points",
                        _or_mp(str(summary.get("evPoints", "—")), "points", mp_s5_bf),
                        _nhl_pct(summary.get("evPoints"), "summary", "evPoints")
                        or _dist_pct(
                            _num_or_mp(summary.get("evPoints"), mp_s5_bf, "points"),
                            "evPoints",
                        ),
                    ),
                    _box(
                        "Shots on Goal",
                        str(sog_val if sog_val is not None else "—"),
                        _nhl_pct(sog_val, "summary", "shots"),
                    ),
                    _box(
                        "Shooting %",
                        _fmt_pct(sh_pct_val),
                        _nhl_pct(
                            sh_pct_val, "summary", "shootingPct", True, min_shots=10
                        ),
                    ),
                    _box(
                        "Game-Winning Goals",
                        str(gwg_val if gwg_val is not None else "—"),
                        _nhl_pct(gwg_val, "summary", "gameWinningGoals"),
                    ),
                    _box(
                        "Overtime Goals",
                        str(otg_val if otg_val is not None else "—"),
                        _nhl_pct(otg_val, "summary", "otGoals"),
                    ),
                    _box(
                        "First Goals",
                        str(rt.get("firstGoals", "—")),
                        _nhl_pct(rt.get("firstGoals"), "realtime", "firstGoals"),
                    ),
                    _box(
                        "Empty-Net Points",
                        str(rt.get("emptyNetPoints", "—")),
                        _nhl_pct(
                            rt.get("emptyNetPoints"), "realtime", "emptyNetPoints"
                        ),
                    ),
                ],
            },
            {
                "title": "Special Teams & Ice Time",
                "items": [
                    _box(
                        "PP Points",
                        _or_mp(
                            str(pp_pts_val if pp_pts_val is not None else "—"),
                            "points",
                            mp_pp_bf,
                        ),
                        _nhl_pct(pp_pts_val, "summary", "ppPoints"),
                        True,
                    ),
                    _box(
                        "PP Goals",
                        _or_mp(
                            str(pp_g_val if pp_g_val is not None else "—"),
                            "goals",
                            mp_pp_bf,
                        ),
                        _nhl_pct(pp_g_val, "summary", "ppGoals")
                        or _dist_pct(
                            _num_or_mp(pp_g_val, mp_pp_bf, "goals"), "ppGoals"
                        ),
                    ),
                    _box(
                        "PP Primary Assists",
                        _or_mp(
                            str(pp.get("ppPrimaryAssists", "—")),
                            "primaryAssists",
                            mp_pp_bf,
                        ),
                        _dist_pct(
                            _num_or_mp(
                                pp.get("ppPrimaryAssists"), mp_pp_bf, "primaryAssists"
                            ),
                            "ppPrimaryAssists",
                        ),
                    ),
                    _box(
                        "PP Points / 60",
                        _or_mp(
                            f"{float(pp['ppPointsPer60']):.2f}"
                            if pp.get("ppPointsPer60") is not None
                            else "—",
                            "pointsPer60",
                            mp_pp_bf,
                        ),
                        _dist_pct(
                            _num_or_mp(
                                pp.get("ppPointsPer60"), mp_pp_bf, "pointsPer60"
                            ),
                            "ppPointsPer60",
                        ),
                    ),
                    _box(
                        "SH Points",
                        _or_mp(
                            str(sh_pts_val if sh_pts_val is not None else "—"),
                            "points",
                            mp_pk_bf,
                        ),
                        _nhl_pct(sh_pts_val, "summary", "shPoints")
                        or _dist_pct(
                            _num_or_mp(sh_pts_val, mp_pk_bf, "points"), "shPoints"
                        ),
                    ),
                    _box(
                        "SH Goals",
                        _or_mp(
                            str(sh_g_val if sh_g_val is not None else "—"),
                            "goals",
                            mp_pk_bf,
                        ),
                        _nhl_pct(sh_g_val, "summary", "shGoals")
                        or _dist_pct(
                            _num_or_mp(sh_g_val, mp_pk_bf, "goals"), "shGoals"
                        ),
                    ),
                    _box(
                        "Total TOI / GP",
                        toi_pg,
                        _nhl_pct(toi_sec, "summary", "timeOnIcePerGame"),
                    ),
                    _box(
                        "Even-Strength TOI / GP",
                        _fmt_toi(ev_toi_sec),
                        _dist_pct(ev_toi_sec, "evToiPerGame"),
                    ),
                    _box(
                        "Power Play TOI / GP",
                        _fmt_toi(pp_toi_sec),
                        _dist_pct(pp_toi_sec, "ppToiPerGame"),
                    ),
                    _box(
                        "Penalty Kill TOI / GP",
                        _fmt_toi(pk_toi_sec),
                        _dist_pct(pk_toi_sec, "pkToiPerGame"),
                    ),
                    _box(
                        "Shifts / GP",
                        _or_mp(
                            f"{float(toi['shiftsPerGame']):.1f}"
                            if toi.get("shiftsPerGame") is not None
                            else "—",
                            "shiftsPerGame",
                            mp_all_bf,
                        ),
                        _dist_pct(
                            _num_or_mp(
                                toi.get("shiftsPerGame"), mp_all_bf, "shiftsPerGame"
                            ),
                            "shiftsPerGame",
                        ),
                    ),
                    _box(
                        "Avg Shift Length",
                        _fmt_toi(avg_shift_sec),
                        _dist_pct(avg_shift_sec, "avgShiftLen"),
                    ),
                ],
            },
            {
                "title": "Possession & On-Ice Analytics (5v5)",
                "items": [
                    _box(
                        "Corsi / SAT %",
                        _or_mp(
                            _fmt_pct(poss.get("satPct", pcts.get("satPct5v5"))),
                            "satPct",
                        ),
                        mp_s5_rk.get("satPct"),
                        True,
                    ),
                    _box(
                        "SAT Relative %",
                        _or_mp(
                            f"{float(poss['satRelative']):+.1f}%"
                            if poss.get("satRelative") is not None
                            else "—",
                            "satRel",
                        ),
                        mp_s5_rk.get("satRel"),
                    ),
                    _box(
                        "Fenwick / USAT %",
                        _or_mp(
                            _fmt_pct(poss.get("usatPct", pcts.get("usatPct5v5"))),
                            "usatPct",
                        ),
                        mp_s5_rk.get("usatPct"),
                    ),
                    _box(
                        "USAT Relative %",
                        _or_mp(
                            f"{float(poss['usatRelative']):+.1f}%"
                            if poss.get("usatRelative") is not None
                            else "—",
                            "usatRel",
                        ),
                        mp_s5_rk.get("usatRel"),
                    ),
                    _box(
                        "SAT For / Against",
                        _or_mp(
                            f"{poss.get('satFor', '—')} / {poss.get('satAgainst', '—')}",
                            "satForAgainst",
                        ),
                        mp_s5_rk.get("satForAgainst"),
                    ),
                    _box(
                        "SAT % Close",
                        _or_mp(_fmt_pct(poss.get("satPctClose")), "satPctClose"),
                        mp_s5_rk.get("satPctClose"),
                    ),
                    _box(
                        "Offensive Zone Start %",
                        _or_mp(
                            _fmt_pct(
                                poss.get("zoneStartPct", pcts.get("zoneStartPct5v5"))
                            ),
                            "ozStartPct",
                        ),
                        mp_s5_rk.get("ozStartPct"),
                    ),
                    _box(
                        "On-Ice Shooting %",
                        _or_mp(_fmt_pct(on_ice_sh), "onIceShPct"),
                        mp_s5_rk.get("onIceShPct"),
                    ),
                    _box(
                        "On-Ice Save %",
                        _or_mp(_fmt_pct(on_ice_sv), "onIceSvPct"),
                        mp_s5_rk.get("onIceSvPct"),
                    ),
                    _box(
                        "PDO (5v5)", _or_mp(pdo_val or "—", "pdo"), mp_s5_rk.get("pdo")
                    ),
                ],
            },
            {
                "title": "Physical, Micro-Stats & Discipline",
                "items": [
                    _box(
                        "Hits",
                        _or_mp(str(rt.get("hits", "—")), "hits", mp_all_bf),
                        _nhl_pct(rt.get("hits"), "realtime", "hits")
                        or _dist_pct(
                            _num_or_mp(rt.get("hits"), mp_all_bf, "hits"), "hits"
                        ),
                    ),
                    _box(
                        "Hits / 60",
                        _or_mp(
                            f"{float(rt['hitsPer60']):.2f}"
                            if rt.get("hitsPer60") is not None
                            else "—",
                            "hitsPer60",
                            mp_all_bf,
                        ),
                        _nhl_pct(
                            rt.get("hitsPer60"), "realtime", "hitsPer60", True, min_gp=5
                        )
                        or _dist_pct(
                            _num_or_mp(rt.get("hitsPer60"), mp_all_bf, "hitsPer60"),
                            "hitsPer60",
                        ),
                    ),
                    _box(
                        "Blocked Shots",
                        _or_mp(
                            str(rt.get("blockedShots", "—")), "blockedShots", mp_all_bf
                        ),
                        _nhl_pct(rt.get("blockedShots"), "realtime", "blockedShots")
                        or _dist_pct(
                            _num_or_mp(
                                rt.get("blockedShots"), mp_all_bf, "blockedShots"
                            ),
                            "blockedShots",
                        ),
                    ),
                    _box(
                        "Blocks / 60",
                        _or_mp(
                            f"{float(rt['blockedShotsPer60']):.2f}"
                            if rt.get("blockedShotsPer60") is not None
                            else "—",
                            "blocksPer60",
                            mp_all_bf,
                        ),
                        _nhl_pct(
                            rt.get("blockedShotsPer60"),
                            "realtime",
                            "blockedShotsPer60",
                            True,
                            min_gp=5,
                        )
                        or _dist_pct(
                            _num_or_mp(
                                rt.get("blockedShotsPer60"), mp_all_bf, "blocksPer60"
                            ),
                            "blocksPer60",
                        ),
                    ),
                    _box(
                        "Takeaways",
                        _or_mp(str(rt.get("takeaways", "—")), "takeaways", mp_all_bf),
                        _nhl_pct(rt.get("takeaways"), "realtime", "takeaways")
                        or _dist_pct(
                            _num_or_mp(rt.get("takeaways"), mp_all_bf, "takeaways"),
                            "takeaways",
                        ),
                    ),
                    _box(
                        "Giveaways",
                        _or_mp(str(rt.get("giveaways", "—")), "giveaways", mp_all_bf),
                        _nhl_pct(
                            rt.get("giveaways"),
                            "realtime",
                            "giveaways",
                            False,
                            min_gp=5,
                        )
                        or _dist_pct(
                            _num_or_mp(rt.get("giveaways"), mp_all_bf, "giveaways"),
                            "giveaways",
                            False,
                        ),
                    ),
                    _box(
                        "Missed Shots",
                        _or_mp(
                            str(rt.get("missedShots", "—")), "missedShots", mp_all_bf
                        ),
                        _nhl_pct(rt.get("missedShots"), "realtime", "missedShots")
                        or _dist_pct(
                            _num_or_mp(rt.get("missedShots"), mp_all_bf, "missedShots"),
                            "missedShots",
                        ),
                    ),
                    _box(
                        "Posts / Crossbars",
                        str(posts_val),
                        _pctile_str(posts_val, posts_pop),
                    ),
                    _box(
                        "Faceoff Win %",
                        _or_mp(
                            _fmt_pct(summary.get("faceoffWinPct")),
                            "faceoffWinPct",
                            mp_all_bf,
                        ),
                        _nhl_pct(
                            summary.get("faceoffWinPct"),
                            "summary",
                            "faceoffWinPct",
                            True,
                            min_gp=5,
                        )
                        or _dist_pct(
                            _num_or_mp(
                                summary.get("faceoffWinPct"), mp_all_bf, "faceoffWinPct"
                            ),
                            "faceoffWinPct",
                        ),
                    ),
                    _box(
                        "Penalty Minutes",
                        _or_mp(
                            str(pim_val if pim_val is not None else "—"),
                            "pim",
                            mp_all_bf,
                        ),
                        _nhl_pct(pim_val, "summary", "penaltyMinutes", False, min_gp=5)
                        or _dist_pct(
                            _num_or_mp(pim_val, mp_all_bf, "pim"), "pim", False
                        ),
                    ),
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
