import csv
import io
import time
import os
from pathlib import Path
from typing import Any, Callable
import httpx
from django.conf import settings
from django.core.cache import cache

MONEYPUCK_BASE = "https://moneypuck.com/moneypuck/playerData/seasonSummary"
CSV_DISK_TTL_SECONDS = 6 * 3600  # Refresh from MoneyPuck at most every 6 hours
MEMORY_TTL_SECONDS = 3600
SITUATIONS = ("5on5", "all", "5on4", "4on5")


def _season_year(season_id: str) -> str:
    s = str(season_id or "20262027")
    return s[:4] if len(s) >= 4 else "2026"


def _data_dir(year: str) -> Path:
    if os.getenv("RENDER"):
        base = Path("/tmp/moneypuck") / year
    else:
        base = Path(getattr(settings, "BASE_DIR", ".")) / "data" / "moneypuck" / year
    base.mkdir(parents=True, exist_ok=True)
    return base


def _f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = row.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _i(row: dict[str, str], key: str, default: int = 0) -> int:
    return int(round(_f(row, key, float(default))))


def _per60(val: float, icetime_sec: float) -> float:
    if icetime_sec <= 0:
        return 0.0
    return val / (icetime_sec / 3600.0)


def _fmt_pct(val: float | None, decimals: int = 1) -> str:
    if val is None:
        return "—"
    num = val * 100.0 if abs(val) <= 1.0 else val
    return f"{num:.{decimals}f}%"


def _fmt_signed_pct(val: float | None, decimals: int = 1) -> str:
    if val is None:
        return "—"
    return f"{val:+.{decimals}f}%"


def _fmt_sv_pct(val: float | None) -> str:
    if val is None:
        return "—"
    num = val / 100.0 if val > 1.0 else val
    return f"{num:.3f}".lstrip("0") if num < 1.0 else f"{num:.3f}"


def _ordinal(n: int | None) -> str | None:
    if n is None:
        return None
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _percentile(
    value: float, population: list[float], higher_is_better: bool = True
) -> int:
    if not population:
        return 50
    if higher_is_better:
        below = sum(1 for v in population if v < value)
        equal = sum(1 for v in population if v == value)
    else:
        below = sum(1 for v in population if v > value)
        equal = sum(1 for v in population if v == value)
    pct = ((below + 0.5 * equal) / len(population)) * 100.0
    return max(1, min(99, int(round(pct))))


def _rank_in_list(
    value: float, population: list[float], higher_is_better: bool = True
) -> int | None:
    if not population:
        return None
    ordered = sorted(population, reverse=higher_is_better)
    for idx, v in enumerate(ordered, start=1):
        if (higher_is_better and value >= v) or (not higher_is_better and value <= v):
            return idx
    return len(ordered)


def _pctile_badge(
    value: float | None,
    peers: list[dict[str, str]],
    extractor: Callable[[dict[str, str]], float | None],
    higher_is_better: bool = True,
) -> str | None:
    if value is None or not peers:
        return None
    pop = [v for p in peers if (v := extractor(p)) is not None]
    if not pop:
        return None
    return f"{_percentile(value, pop, higher_is_better)}%ile"


def _team_rank_badge(
    value: float | None,
    peers: list[dict[str, str]],
    extractor: Callable[[dict[str, str]], float | None],
    higher_is_better: bool = True,
) -> str | None:
    if value is None or not peers:
        return None
    pop = [v for p in peers if (v := extractor(p)) is not None]
    if not pop:
        return None
    return _ordinal(_rank_in_list(value, pop, higher_is_better))


def download_moneypuck_csv(dataset: str, season_id: str, force: bool = False) -> Path:
    """
    Download an official season-level CSV listed on https://moneypuck.com/data.htm
    ('skaters', 'goalies', or 'teams') and cache it on disk.
    """
    year = _season_year(season_id)
    dest = _data_dir(year) / f"{dataset}.csv"

    if (
        not force
        and dest.exists()
        and dest.stat().st_size > 0
        and (time.time() - dest.stat().st_mtime) < CSV_DISK_TTL_SECONDS
    ):
        return dest

    url = f"{MONEYPUCK_BASE}/{year}/regular/{dataset}.csv"
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "NHL-Analytics-App/1.0 (+MoneyPuck Data Consumer)"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            cache.delete(f"mp_dataset_v1_{year}_{dataset}")
    except httpx.HTTPError:
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        raise
    return dest


def _load_dataset(dataset: str, season_id: str) -> list[dict[str, str]]:
    year = _season_year(season_id)
    mem_key = f"mp_dataset_v1_{year}_{dataset}"
    cached = cache.get(mem_key)
    if cached is not None:
        return cached

    try:
        csv_path = download_moneypuck_csv(dataset, season_id, force=False)
        text = csv_path.read_text(encoding="utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception:
        rows = []

    if rows:
        cache.set(mem_key, rows, MEMORY_TTL_SECONDS)
    return rows


def refresh_all_moneypuck(season_id: str) -> dict[str, int]:
    """Force-refresh all three MoneyPuck season CSVs for the active season."""
    counts: dict[str, int] = {}
    year = _season_year(season_id)
    for ds in ("skaters", "goalies", "teams"):
        csv_path = download_moneypuck_csv(ds, season_id, force=True)
        text = csv_path.read_text(encoding="utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        cache.set(f"mp_dataset_v1_{year}_{ds}", rows, MEMORY_TTL_SECONDS)
        counts[ds] = len(rows)
    cache.delete(f"mp_skater_dists_v1_{year}")
    return counts


def get_skater_league_distributions(season_id: str) -> dict[str, list[float]]:
    """
    Cached league-wide numeric distributions derived from MoneyPuck skaters.csv
    so nhl_player_profile.py can compute instant percentiles without extra API calls.
    """
    year = _season_year(season_id)
    mem_key = f"mp_skater_dists_v1_{year}"
    cached = cache.get(mem_key)
    if cached is not None:
        return cached

    rows = _load_dataset("skaters", season_id)
    if not rows:
        return {}

    by_sit: dict[str, list[dict[str, str]]] = {s: [] for s in SITUATIONS}
    for r in rows:
        sit = r.get("situation", "")
        if sit in by_sit:
            by_sit[sit].append(r)

    all_rows = by_sit["all"]
    s5_rows = by_sit["5on5"]
    pp_rows = by_sit["5on4"]
    pk_rows = by_sit["4on5"]

    qual_all = [r for r in all_rows if _f(r, "icetime") >= 900.0] or all_rows
    qual_5v5 = [r for r in s5_rows if _f(r, "icetime") >= 900.0] or s5_rows
    qual_pp = [r for r in pp_rows if _f(r, "icetime") >= 300.0] or pp_rows

    dists: dict[str, list[float]] = {
        "evGoals": [_f(r, "I_F_goals") for r in s5_rows],
        "evPoints": [_f(r, "I_F_points") for r in s5_rows],
        "ppGoals": [_f(r, "I_F_goals") for r in pp_rows],
        "ppPrimaryAssists": [_f(r, "I_F_primaryAssists") for r in pp_rows],
        "ppPointsPer60": [
            _per60(_f(r, "I_F_points"), _f(r, "icetime")) for r in qual_pp
        ],
        "shPoints": [_f(r, "I_F_points") for r in pk_rows],
        "shGoals": [_f(r, "I_F_goals") for r in pk_rows],
        "evToiPerGame": [
            _f(r, "icetime") / max(1.0, _f(r, "games_played", 1.0)) for r in s5_rows
        ],
        "ppToiPerGame": [
            _f(r, "icetime") / max(1.0, _f(r, "games_played", 1.0)) for r in pp_rows
        ],
        "pkToiPerGame": [
            _f(r, "icetime") / max(1.0, _f(r, "games_played", 1.0)) for r in pk_rows
        ],
        "shiftsPerGame": [
            _f(r, "shifts") / max(1.0, _f(r, "games_played", 1.0)) for r in all_rows
        ],
        "avgShiftLen": [
            _f(r, "icetime") / _f(r, "shifts") for r in qual_all if _f(r, "shifts") > 0
        ],
        "hits": [_f(r, "I_F_hits") for r in all_rows],
        "hitsPer60": [_per60(_f(r, "I_F_hits"), _f(r, "icetime")) for r in qual_all],
        "blockedShots": [_f(r, "shotsBlockedByPlayer") for r in all_rows],
        "blocksPer60": [
            _per60(_f(r, "shotsBlockedByPlayer"), _f(r, "icetime")) for r in qual_all
        ],
        "takeaways": [_f(r, "I_F_takeaways") for r in all_rows],
        "giveaways": [_f(r, "I_F_giveaways") for r in qual_all],
        "missedShots": [_f(r, "I_F_missedShots") for r in all_rows],
        "pim": [_f(r, "penalityMinutes") for r in qual_all],
        "faceoffWinPct": [
            _f(r, "faceoffsWon") / (_f(r, "faceoffsWon") + _f(r, "faceoffsLost"))
            for r in all_rows
            if (_f(r, "faceoffsWon") + _f(r, "faceoffsLost")) >= 20
        ],
        "satPct5v5": [_f(r, "onIce_corsiPercentage") for r in qual_5v5],
        "satRel5v5": [
            (_f(r, "onIce_corsiPercentage") - _f(r, "offIce_corsiPercentage")) * 100.0
            for r in qual_5v5
        ],
        "usatPct5v5": [_f(r, "onIce_fenwickPercentage") for r in qual_5v5],
        "usatRel5v5": [
            (_f(r, "onIce_fenwickPercentage") - _f(r, "offIce_fenwickPercentage"))
            * 100.0
            for r in qual_5v5
        ],
        "satDiff5v5": [
            _f(r, "OnIce_F_shotAttempts") - _f(r, "OnIce_A_shotAttempts")
            for r in qual_5v5
        ],
        "satClose5v5": [
            _f(r, "OnIce_F_scoreAdjustedShotsAttempts")
            / (
                _f(r, "OnIce_F_scoreAdjustedShotsAttempts")
                + _f(r, "OnIce_A_scoreAdjustedShotsAttempts")
            )
            for r in qual_5v5
            if (
                _f(r, "OnIce_F_scoreAdjustedShotsAttempts")
                + _f(r, "OnIce_A_scoreAdjustedShotsAttempts")
            )
            > 0
        ],
        "ozStart5v5": [
            _f(r, "I_F_oZoneShiftStarts")
            / (_f(r, "I_F_oZoneShiftStarts") + _f(r, "I_F_dZoneShiftStarts"))
            for r in qual_5v5
            if (_f(r, "I_F_oZoneShiftStarts") + _f(r, "I_F_dZoneShiftStarts")) > 0
        ],
        "onIceSh5v5": [
            _f(r, "OnIce_F_goals") / _f(r, "OnIce_F_shotsOnGoal")
            for r in qual_5v5
            if _f(r, "OnIce_F_shotsOnGoal") > 0
        ],
        "onIceSv5v5": [
            1.0 - (_f(r, "OnIce_A_goals") / _f(r, "OnIce_A_shotsOnGoal"))
            for r in qual_5v5
            if _f(r, "OnIce_A_shotsOnGoal") > 0
        ],
        "pdo5v5": [
            (
                (_f(r, "OnIce_F_goals") / _f(r, "OnIce_F_shotsOnGoal"))
                + (1.0 - (_f(r, "OnIce_A_goals") / _f(r, "OnIce_A_shotsOnGoal")))
            )
            * 100.0
            for r in qual_5v5
            if _f(r, "OnIce_F_shotsOnGoal") > 0 and _f(r, "OnIce_A_shotsOnGoal") > 0
        ],
    }

    cache.set(mem_key, dists, MEMORY_TTL_SECONDS)
    return dists


# ==============================================================================
# SKATER ANALYTICS
# ==============================================================================


def _build_skater_situation(
    row: dict[str, str], peers: list[dict[str, str]]
) -> dict[str, Any]:
    toi = _f(row, "icetime")
    gp = max(1, _i(row, "games_played", 1))
    ixg = _f(row, "I_F_xGoals")
    goals = _f(row, "I_F_goals")
    g_above_exp = goals - ixg
    p_assists = _i(row, "I_F_primaryAssists")
    s_assists = _i(row, "I_F_secondaryAssists")
    prim_pts_60 = _per60(goals + p_assists, toi)
    ixg_60 = _per60(ixg, toi)
    goals_60 = _per60(goals, toi)
    gs = _f(row, "gameScore")
    gs_60 = _per60(gs, toi)

    on_xg_pct = _f(row, "onIce_xGoalsPercentage")
    off_xg_pct = _f(row, "offIce_xGoalsPercentage")
    xg_rel = (on_xg_pct - off_xg_pct) * 100.0

    on_cf_pct = _f(row, "onIce_corsiPercentage")
    off_cf_pct = _f(row, "offIce_corsiPercentage")
    cf_rel = (on_cf_pct - off_cf_pct) * 100.0

    on_ff_pct = _f(row, "onIce_fenwickPercentage")
    off_ff_pct = _f(row, "offIce_fenwickPercentage")
    ff_rel = (on_ff_pct - off_ff_pct) * 100.0

    on_xgf = _f(row, "OnIce_F_xGoals")
    on_xga = _f(row, "OnIce_A_xGoals")
    on_xgf_60 = _per60(on_xgf, toi)
    on_xga_60 = _per60(on_xga, toi)

    on_cf = _i(row, "OnIce_F_shotAttempts")
    on_ca = _i(row, "OnIce_A_shotAttempts")
    sa_cf = _f(row, "OnIce_F_scoreAdjustedShotsAttempts")
    sa_ca = _f(row, "OnIce_A_scoreAdjustedShotsAttempts")
    sa_cf_pct = (sa_cf / (sa_cf + sa_ca)) if (sa_cf + sa_ca) > 0 else None

    on_gf = _i(row, "OnIce_F_goals")
    on_ga = _i(row, "OnIce_A_goals")
    on_sog_f = _f(row, "OnIce_F_shotsOnGoal")
    on_sog_a = _f(row, "OnIce_A_shotsOnGoal")
    on_sh_pct = (on_gf / on_sog_f) if on_sog_f > 0 else None
    on_sv_pct = (1.0 - (on_ga / on_sog_a)) if on_sog_a > 0 else None

    oz_starts = _i(row, "I_F_oZoneShiftStarts")
    dz_starts = _i(row, "I_F_dZoneShiftStarts")
    nz_starts = _i(row, "I_F_neutralZoneShiftStarts")
    fly_starts = _i(row, "I_F_flyShiftStarts")
    oz_start_pct = (
        (oz_starts / (oz_starts + dz_starts)) if (oz_starts + dz_starts) > 0 else None
    )

    fo_w = _i(row, "faceoffsWon")
    fo_l = _i(row, "faceoffsLost")
    fo_pct = (fo_w / (fo_w + fo_l)) if (fo_w + fo_l) > 0 else None

    pen_drawn = _i(row, "penaltiesDrawn")
    pen_taken = _i(row, "penalties")
    after_xg_diff = _f(row, "xGoalsForAfterShifts") - _f(
        row, "xGoalsAgainstAfterShifts"
    )

    # Peer percentiles (qualified skaters with >= 15 min in 5v5/all, >= 5 min in PP/PK)
    min_toi = 900.0 if row.get("situation") in ("5on5", "all") else 300.0
    qual = [p for p in peers if _f(p, "icetime") >= min_toi]
    if len(qual) < 20:
        qual = peers

    def _p(
        val: float | None,
        fn: Callable[[dict[str, str]], float | None],
        higher: bool = True,
        pool: list[dict[str, str]] | None = None,
    ) -> str | None:
        return _pctile_badge(val, pool if pool is not None else qual, fn, higher)

    def _sa_cf_fn(r: dict[str, str]) -> float | None:
        f_v = _f(r, "OnIce_F_scoreAdjustedShotsAttempts")
        a_v = _f(r, "OnIce_A_scoreAdjustedShotsAttempts")
        return (f_v / (f_v + a_v)) if (f_v + a_v) > 0 else None

    def _fo_fn(r: dict[str, str]) -> float | None:
        w = _f(r, "faceoffsWon")
        l = _f(r, "faceoffsLost")
        return (w / (w + l)) if (w + l) >= 15 else None

    def _oz_pct_fn(r: dict[str, str]) -> float | None:
        oz = _f(r, "I_F_oZoneShiftStarts")
        dz = _f(r, "I_F_dZoneShiftStarts")
        return (oz / (oz + dz)) if (oz + dz) > 0 else None

    def _on_sh_fn(r: dict[str, str]) -> float | None:
        sog = _f(r, "OnIce_F_shotsOnGoal")
        return (_f(r, "OnIce_F_goals") / sog) if sog > 0 else None

    def _on_sv_fn(r: dict[str, str]) -> float | None:
        sog = _f(r, "OnIce_A_shotsOnGoal")
        return (1.0 - (_f(r, "OnIce_A_goals") / sog)) if sog > 0 else None

    def _pdo_fn(r: dict[str, str]) -> float | None:
        sh = _on_sh_fn(r)
        sv = _on_sv_fn(r)
        return (sh + sv) * 100.0 if sh is not None and sv is not None else None

    finishing_pop = [_f(p, "I_F_goals") - _f(p, "I_F_xGoals") for p in qual]
    ixg60_pop = [_per60(_f(p, "I_F_xGoals"), _f(p, "icetime")) for p in qual]
    prim_a60_pop = [_per60(_f(p, "I_F_primaryAssists"), _f(p, "icetime")) for p in qual]
    cf_pop = [_f(p, "onIce_corsiPercentage") for p in qual]
    xg_pop = [_f(p, "onIce_xGoalsPercentage") for p in qual]
    xga60_pop = [_per60(_f(p, "OnIce_A_xGoals"), _f(p, "icetime")) for p in qual]

    radar = [
        {
            "axis": "Finishing",
            "percentile": _percentile(g_above_exp, finishing_pop, True),
            "display": f"{g_above_exp:+.2f} G-xG",
        },
        {
            "axis": "Shot Quality",
            "percentile": _percentile(ixg_60, ixg60_pop, True),
            "display": f"{ixg_60:.2f} ixG/60",
        },
        {
            "axis": "Playmaking",
            "percentile": _percentile(_per60(p_assists, toi), prim_a60_pop, True),
            "display": f"{_per60(p_assists, toi):.2f} A1/60",
        },
        {
            "axis": "Possession",
            "percentile": _percentile(on_cf_pct, cf_pop, True),
            "display": _fmt_pct(on_cf_pct),
        },
        {
            "axis": "On-Ice xG%",
            "percentile": _percentile(on_xg_pct, xg_pop, True),
            "display": _fmt_pct(on_xg_pct),
        },
        {
            "axis": "Defense",
            "percentile": _percentile(on_xga_60, xga60_pop, False),
            "display": f"{on_xga_60:.2f} xGA/60",
        },
    ]

    danger_bars = [
        {
            "zone": "Low Danger",
            "shots": _i(row, "I_F_lowDangerShots"),
            "expected": round(_f(row, "I_F_lowDangerxGoals"), 2),
            "actual": _i(row, "I_F_lowDangerGoals"),
        },
        {
            "zone": "Medium Danger",
            "shots": _i(row, "I_F_mediumDangerShots"),
            "expected": round(_f(row, "I_F_mediumDangerxGoals"), 2),
            "actual": _i(row, "I_F_mediumDangerGoals"),
        },
        {
            "zone": "High Danger",
            "shots": _i(row, "I_F_highDangerShots"),
            "expected": round(_f(row, "I_F_highDangerxGoals"), 2),
            "actual": _i(row, "I_F_highDangerGoals"),
        },
    ]

    on_off_impact = [
        {
            "label": "Expected Goals %",
            "onIce": round(on_xg_pct * 100.0, 1),
            "offIce": round(off_xg_pct * 100.0, 1),
            "rel": round(xg_rel, 1),
        },
        {
            "label": "Corsi (SAT %)",
            "onIce": round(on_cf_pct * 100.0, 1),
            "offIce": round(off_cf_pct * 100.0, 1),
            "rel": round(cf_rel, 1),
        },
        {
            "label": "Fenwick (USAT %)",
            "onIce": round(on_ff_pct * 100.0, 1),
            "offIce": round(off_ff_pct * 100.0, 1),
            "rel": round(ff_rel, 1),
        },
    ]

    shift_starts = [
        {"label": "O-Zone", "count": oz_starts},
        {"label": "N-Zone", "count": nz_starts},
        {"label": "D-Zone", "count": dz_starts},
        {"label": "On-the-Fly", "count": fly_starts},
    ]

    stat_groups = [
        {
            "title": "Expected Goals & Finishing",
            "items": [
                {
                    "label": "Individual xG (ixG)",
                    "value": f"{ixg:.2f}",
                    "rank": _p(ixg, lambda r: _f(r, "I_F_xGoals")),
                    "highlight": True,
                },
                {
                    "label": "Goals Above Exp.",
                    "value": f"{g_above_exp:+.2f}",
                    "rank": _p(
                        g_above_exp, lambda r: _f(r, "I_F_goals") - _f(r, "I_F_xGoals")
                    ),
                    "highlight": g_above_exp > 0,
                },
                {
                    "label": "Flurry-Adj xG",
                    "value": f"{_f(row, 'I_F_flurryAdjustedxGoals'):.2f}",
                    "rank": _p(
                        _f(row, "I_F_flurryAdjustedxGoals"),
                        lambda r: _f(r, "I_F_flurryAdjustedxGoals"),
                    ),
                },
                {
                    "label": "Score/Venue-Adj xG",
                    "value": f"{_f(row, 'I_F_scoreVenueAdjustedxGoals'):.2f}",
                    "rank": _p(
                        _f(row, "I_F_scoreVenueAdjustedxGoals"),
                        lambda r: _f(r, "I_F_scoreVenueAdjustedxGoals"),
                    ),
                },
                {
                    "label": "xG w/ Earned Reb.",
                    "value": f"{_f(row, 'I_F_xGoals_with_earned_rebounds'):.2f}",
                    "rank": _p(
                        _f(row, "I_F_xGoals_with_earned_rebounds"),
                        lambda r: _f(r, "I_F_xGoals_with_earned_rebounds"),
                    ),
                },
                {
                    "label": "Game Score",
                    "value": f"{gs:.2f}",
                    "rank": _p(gs, lambda r: _f(r, "gameScore")),
                    "highlight": True,
                },
                {
                    "label": "Game Score / 60",
                    "value": f"{gs_60:.2f}",
                    "rank": _p(
                        gs_60, lambda r: _per60(_f(r, "gameScore"), _f(r, "icetime"))
                    ),
                },
                {
                    "label": "ixG / 60",
                    "value": f"{ixg_60:.2f}",
                    "rank": _p(
                        ixg_60, lambda r: _per60(_f(r, "I_F_xGoals"), _f(r, "icetime"))
                    ),
                },
                {
                    "label": "Goals / 60",
                    "value": f"{goals_60:.2f}",
                    "rank": _p(
                        goals_60, lambda r: _per60(_f(r, "I_F_goals"), _f(r, "icetime"))
                    ),
                },
                {
                    "label": "Primary Assists",
                    "value": str(p_assists),
                    "rank": _p(float(p_assists), lambda r: _f(r, "I_F_primaryAssists")),
                },
                {
                    "label": "Secondary Assists",
                    "value": str(s_assists),
                    "rank": _p(
                        float(s_assists), lambda r: _f(r, "I_F_secondaryAssists")
                    ),
                },
                {
                    "label": "Primary Pts / 60",
                    "value": f"{prim_pts_60:.2f}",
                    "rank": _p(
                        prim_pts_60,
                        lambda r: _per60(
                            _f(r, "I_F_goals") + _f(r, "I_F_primaryAssists"),
                            _f(r, "icetime"),
                        ),
                    ),
                },
            ],
        },
        {
            "title": "On-Ice Impact & Relative Metrics",
            "items": [
                {
                    "label": "On-Ice xG %",
                    "value": _fmt_pct(on_xg_pct),
                    "rank": _p(on_xg_pct, lambda r: _f(r, "onIce_xGoalsPercentage")),
                    "highlight": True,
                },
                {
                    "label": "Off-Ice xG %",
                    "value": _fmt_pct(off_xg_pct),
                    "rank": _p(off_xg_pct, lambda r: _f(r, "offIce_xGoalsPercentage")),
                },
                {
                    "label": "xG % Relative",
                    "value": _fmt_signed_pct(xg_rel),
                    "rank": _p(
                        xg_rel,
                        lambda r: (
                            (
                                _f(r, "onIce_xGoalsPercentage")
                                - _f(r, "offIce_xGoalsPercentage")
                            )
                            * 100.0
                        ),
                    ),
                    "highlight": xg_rel > 0,
                },
                {
                    "label": "On-Ice xGF / 60",
                    "value": f"{on_xgf_60:.2f}",
                    "rank": _p(
                        on_xgf_60,
                        lambda r: _per60(_f(r, "OnIce_F_xGoals"), _f(r, "icetime")),
                    ),
                },
                {
                    "label": "On-Ice xGA / 60",
                    "value": f"{on_xga_60:.2f}",
                    "rank": _p(
                        on_xga_60,
                        lambda r: _per60(_f(r, "OnIce_A_xGoals"), _f(r, "icetime")),
                        False,
                    ),
                },
                {
                    "label": "On-Ice xG Diff / 60",
                    "value": f"{(on_xgf_60 - on_xga_60):+.2f}",
                    "rank": _p(
                        on_xgf_60 - on_xga_60,
                        lambda r: _per60(
                            _f(r, "OnIce_F_xGoals") - _f(r, "OnIce_A_xGoals"),
                            _f(r, "icetime"),
                        ),
                    ),
                },
                {
                    "label": "Corsi Relative %",
                    "value": _fmt_signed_pct(cf_rel),
                    "rank": _p(
                        cf_rel,
                        lambda r: (
                            (
                                _f(r, "onIce_corsiPercentage")
                                - _f(r, "offIce_corsiPercentage")
                            )
                            * 100.0
                        ),
                    ),
                },
                {
                    "label": "Fenwick Relative %",
                    "value": _fmt_signed_pct(ff_rel),
                    "rank": _p(
                        ff_rel,
                        lambda r: (
                            (
                                _f(r, "onIce_fenwickPercentage")
                                - _f(r, "offIce_fenwickPercentage")
                            )
                            * 100.0
                        ),
                    ),
                },
                {
                    "label": "Score-Adj SAT %",
                    "value": _fmt_pct(sa_cf_pct),
                    "rank": _p(sa_cf_pct, _sa_cf_fn),
                },
                {
                    "label": "On-Ice GF / GA",
                    "value": f"{on_gf} / {on_ga}",
                    "rank": _p(
                        float(on_gf - on_ga),
                        lambda r: _f(r, "OnIce_F_goals") - _f(r, "OnIce_A_goals"),
                    ),
                },
                {
                    "label": "After-Shift xG Diff",
                    "value": f"{after_xg_diff:+.2f}",
                    "rank": _p(
                        after_xg_diff,
                        lambda r: (
                            _f(r, "xGoalsForAfterShifts")
                            - _f(r, "xGoalsAgainstAfterShifts")
                        ),
                    ),
                },
                {
                    "label": "Team TOI Rank",
                    "value": _ordinal(_i(row, "iceTimeRank")) or "—",
                    "rank": _p(toi, lambda r: _f(r, "icetime")),
                },
            ],
        },
        {
            "title": "Shot Danger & Rebound Creation",
            "items": [
                {
                    "label": "High-Danger Shots",
                    "value": str(_i(row, "I_F_highDangerShots")),
                    "rank": _p(
                        _f(row, "I_F_highDangerShots"),
                        lambda r: _f(r, "I_F_highDangerShots"),
                    ),
                    "highlight": True,
                },
                {
                    "label": "High-Danger xG",
                    "value": f"{_f(row, 'I_F_highDangerxGoals'):.2f}",
                    "rank": _p(
                        _f(row, "I_F_highDangerxGoals"),
                        lambda r: _f(r, "I_F_highDangerxGoals"),
                    ),
                },
                {
                    "label": "High-Danger Goals",
                    "value": str(_i(row, "I_F_highDangerGoals")),
                    "rank": _p(
                        _f(row, "I_F_highDangerGoals"),
                        lambda r: _f(r, "I_F_highDangerGoals"),
                    ),
                },
                {
                    "label": "Med-Danger Shots",
                    "value": str(_i(row, "I_F_mediumDangerShots")),
                    "rank": _p(
                        _f(row, "I_F_mediumDangerShots"),
                        lambda r: _f(r, "I_F_mediumDangerShots"),
                    ),
                },
                {
                    "label": "Med-Danger xG",
                    "value": f"{_f(row, 'I_F_mediumDangerxGoals'):.2f}",
                    "rank": _p(
                        _f(row, "I_F_mediumDangerxGoals"),
                        lambda r: _f(r, "I_F_mediumDangerxGoals"),
                    ),
                },
                {
                    "label": "Med-Danger Goals",
                    "value": str(_i(row, "I_F_mediumDangerGoals")),
                    "rank": _p(
                        _f(row, "I_F_mediumDangerGoals"),
                        lambda r: _f(r, "I_F_mediumDangerGoals"),
                    ),
                },
                {
                    "label": "Low-Danger Shots",
                    "value": str(_i(row, "I_F_lowDangerShots")),
                    "rank": _p(
                        _f(row, "I_F_lowDangerShots"),
                        lambda r: _f(r, "I_F_lowDangerShots"),
                    ),
                },
                {
                    "label": "Rebounds Created",
                    "value": str(_i(row, "I_F_rebounds")),
                    "rank": _p(
                        _f(row, "I_F_rebounds"), lambda r: _f(r, "I_F_rebounds")
                    ),
                },
                {
                    "label": "Rebound Goals",
                    "value": str(_i(row, "I_F_reboundGoals")),
                    "rank": _p(
                        _f(row, "I_F_reboundGoals"), lambda r: _f(r, "I_F_reboundGoals")
                    ),
                },
                {
                    "label": "xG from Rebounds",
                    "value": f"{_f(row, 'I_F_xGoalsFromxReboundsOfShots'):.2f}",
                    "rank": _p(
                        _f(row, "I_F_xGoalsFromxReboundsOfShots"),
                        lambda r: _f(r, "I_F_xGoalsFromxReboundsOfShots"),
                    ),
                },
                {
                    "label": "Expected On-Goal",
                    "value": f"{_f(row, 'I_F_xOnGoal'):.1f}",
                    "rank": _p(_f(row, "I_F_xOnGoal"), lambda r: _f(r, "I_F_xOnGoal")),
                },
                {
                    "label": "D-Zone Giveaways",
                    "value": str(_i(row, "I_F_dZoneGiveaways")),
                    "rank": _p(
                        _f(row, "I_F_dZoneGiveaways"),
                        lambda r: _f(r, "I_F_dZoneGiveaways"),
                        False,
                    ),
                },
            ],
        },
        {
            "title": "Deployment, Shifts & Discipline",
            "items": [
                {
                    "label": "O-Zone Starts",
                    "value": str(oz_starts),
                    "rank": _p(
                        float(oz_starts), lambda r: _f(r, "I_F_oZoneShiftStarts")
                    ),
                },
                {
                    "label": "D-Zone Starts",
                    "value": str(dz_starts),
                    "rank": _p(
                        float(dz_starts), lambda r: _f(r, "I_F_dZoneShiftStarts")
                    ),
                },
                {
                    "label": "N-Zone Starts",
                    "value": str(nz_starts),
                    "rank": _p(
                        float(nz_starts), lambda r: _f(r, "I_F_neutralZoneShiftStarts")
                    ),
                },
                {
                    "label": "On-the-Fly Starts",
                    "value": str(fly_starts),
                    "rank": _p(
                        float(fly_starts), lambda r: _f(r, "I_F_flyShiftStarts")
                    ),
                },
                {
                    "label": "O-Zone Shift Ends",
                    "value": str(_i(row, "I_F_oZoneShiftEnds")),
                    "rank": _p(
                        _f(row, "I_F_oZoneShiftEnds"),
                        lambda r: _f(r, "I_F_oZoneShiftEnds"),
                    ),
                },
                {
                    "label": "D-Zone Shift Ends",
                    "value": str(_i(row, "I_F_dZoneShiftEnds")),
                    "rank": _p(
                        _f(row, "I_F_dZoneShiftEnds"),
                        lambda r: _f(r, "I_F_dZoneShiftEnds"),
                    ),
                },
                {
                    "label": "Penalties Drawn",
                    "value": str(pen_drawn),
                    "rank": _p(float(pen_drawn), lambda r: _f(r, "penaltiesDrawn")),
                    "highlight": pen_drawn > pen_taken,
                },
                {
                    "label": "Penalties Taken",
                    "value": str(pen_taken),
                    "rank": _p(float(pen_taken), lambda r: _f(r, "penalties"), False),
                },
                {
                    "label": "Net Penalties",
                    "value": f"{(pen_drawn - pen_taken):+d}",
                    "rank": _p(
                        float(pen_drawn - pen_taken),
                        lambda r: _f(r, "penaltiesDrawn") - _f(r, "penalties"),
                    ),
                },
                {
                    "label": "PIM Drawn",
                    "value": str(_i(row, "penalityMinutesDrawn")),
                    "rank": _p(
                        _f(row, "penalityMinutesDrawn"),
                        lambda r: _f(r, "penalityMinutesDrawn"),
                    ),
                },
                {
                    "label": "Shots Blocked",
                    "value": str(_i(row, "shotsBlockedByPlayer")),
                    "rank": _p(
                        _f(row, "shotsBlockedByPlayer"),
                        lambda r: _f(r, "shotsBlockedByPlayer"),
                    ),
                },
                {
                    "label": "Faceoff Win %",
                    "value": _fmt_pct(fo_pct),
                    "rank": _p(fo_pct, _fo_fn, True, peers),
                },
            ],
        },
    ]

    pdo_num = (
        (on_sh_pct + on_sv_pct) * 100.0
        if on_sh_pct is not None and on_sv_pct is not None
        else None
    )

    return {
        "statGroups": stat_groups,
        "charts": {
            "radar": radar,
            "dangerBars": danger_bars,
            "onOffImpact": on_off_impact,
            "shiftStarts": shift_starts,
            "expectedVsActual": [
                {
                    "label": "Individual Scoring",
                    "expected": round(ixg, 2),
                    "actual": round(goals, 2),
                    "delta": round(g_above_exp, 2),
                    "deltaLabel": "G − xG",
                },
                {
                    "label": "On-Ice Offense",
                    "expected": round(on_xgf, 2),
                    "actual": float(on_gf),
                    "delta": round(on_gf - on_xgf, 2),
                    "deltaLabel": "GF − xGF",
                },
                {
                    "label": "On-Ice Defense",
                    "expected": round(on_xga, 2),
                    "actual": float(on_ga),
                    "delta": round(on_xga - on_ga, 2),
                    "deltaLabel": "xGA − GA",
                },
            ],
        },
        "backfill": {
            "satPct": _fmt_pct(on_cf_pct),
            "satRel": _fmt_signed_pct(cf_rel),
            "usatPct": _fmt_pct(on_ff_pct),
            "usatRel": _fmt_signed_pct(ff_rel),
            "satForAgainst": f"{on_cf} / {on_ca}",
            "satPctClose": _fmt_pct(sa_cf_pct),
            "ozStartPct": _fmt_pct(oz_start_pct),
            "onIceShPct": _fmt_pct(on_sh_pct),
            "onIceSvPct": _fmt_pct(on_sv_pct),
            "pdo": f"{pdo_num:.1f}" if pdo_num is not None else None,
            "gp": gp,
            "goals": str(int(round(goals))),
            "points": str(_i(row, "I_F_points")),
            "primaryAssists": str(p_assists),
            "pointsPer60": f"{_per60(_f(row, 'I_F_points'), toi):.2f}",
            "toiPerGame": toi / gp,
            "shiftsPerGame": f"{(_f(row, 'shifts') / gp):.1f}",
            "avgShiftLen": (toi / _f(row, "shifts")) if _f(row, "shifts") > 0 else None,
            "hits": str(_i(row, "I_F_hits")),
            "hitsPer60": f"{_per60(_f(row, 'I_F_hits'), toi):.2f}",
            "blockedShots": str(_i(row, "shotsBlockedByPlayer")),
            "blocksPer60": f"{_per60(_f(row, 'shotsBlockedByPlayer'), toi):.2f}",
            "takeaways": str(_i(row, "I_F_takeaways")),
            "giveaways": str(_i(row, "I_F_giveaways")),
            "missedShots": str(_i(row, "I_F_missedShots")),
            "faceoffWinPct": _fmt_pct(fo_pct),
            "pim": str(_i(row, "penalityMinutes")),
        },
        "backfillRanks": {
            "satPct": _p(on_cf_pct, lambda r: _f(r, "onIce_corsiPercentage")),
            "satRel": _p(
                cf_rel,
                lambda r: (
                    (_f(r, "onIce_corsiPercentage") - _f(r, "offIce_corsiPercentage"))
                    * 100.0
                ),
            ),
            "usatPct": _p(on_ff_pct, lambda r: _f(r, "onIce_fenwickPercentage")),
            "usatRel": _p(
                ff_rel,
                lambda r: (
                    (
                        _f(r, "onIce_fenwickPercentage")
                        - _f(r, "offIce_fenwickPercentage")
                    )
                    * 100.0
                ),
            ),
            "satForAgainst": _p(
                float(on_cf - on_ca),
                lambda r: _f(r, "OnIce_F_shotAttempts") - _f(r, "OnIce_A_shotAttempts"),
            ),
            "satPctClose": _p(sa_cf_pct, _sa_cf_fn),
            "ozStartPct": _p(oz_start_pct, _oz_pct_fn),
            "onIceShPct": _p(on_sh_pct, _on_sh_fn),
            "onIceSvPct": _p(on_sv_pct, _on_sv_fn),
            "pdo": _p(pdo_num, _pdo_fn),
        },
    }


def get_skater_moneypuck(player_id: int, season_id: str) -> dict[str, Any] | None:
    rows = _load_dataset("skaters", season_id)
    if not rows:
        return None

    pid_str = str(player_id)
    by_sit: dict[str, dict[str, str]] = {}
    peers_by_sit: dict[str, list[dict[str, str]]] = {s: [] for s in SITUATIONS}

    for r in rows:
        sit = r.get("situation", "")
        if sit in peers_by_sit:
            peers_by_sit[sit].append(r)
        if r.get("playerId") == pid_str and sit in SITUATIONS:
            by_sit[sit] = r

    if not by_sit:
        return None

    situations_out = {
        sit: _build_skater_situation(by_sit[sit], peers_by_sit[sit])
        for sit in SITUATIONS
        if sit in by_sit
    }
    return {
        "source": "MoneyPuck.com",
        "defaultSituation": "5on5"
        if "5on5" in situations_out
        else next(iter(situations_out)),
        "situations": situations_out,
    }


# ==============================================================================
# GOALIE ANALYTICS
# ==============================================================================


def _danger_sv(shots: float, goals: float) -> float | None:
    if shots <= 0:
        return None
    return (shots - goals) / shots


def _build_goalie_situation(
    row: dict[str, str], peers: list[dict[str, str]]
) -> dict[str, Any]:
    toi = _f(row, "icetime")
    xga = _f(row, "xGoals")
    flurry_xga = _f(row, "flurryAdjustedxGoals")
    ga = _f(row, "goals")
    gsax = xga - ga
    flurry_gsax = flurry_xga - ga
    gsax_60 = _per60(gsax, toi)

    sog = _f(row, "ongoal")
    unblocked = _f(row, "unblocked_shot_attempts")
    x_on_goal = _f(row, "xOnGoal")
    exp_sv_sog = (sog - xga) / sog if sog > 0 else None
    act_sv_sog = (sog - ga) / sog if sog > 0 else None
    exp_unblocked_sv = (unblocked - xga) / unblocked if unblocked > 0 else None
    act_unblocked_sv = (unblocked - ga) / unblocked if unblocked > 0 else None
    xg_per_shot = (xga / sog) if sog > 0 else None

    reb = _f(row, "rebounds")
    x_reb = _f(row, "xRebounds")
    reb_diff = x_reb - reb  # positive = fewer rebounds allowed than expected

    frz = _f(row, "freeze")
    x_frz = _f(row, "xFreeze")
    frz_diff = frz - x_frz  # positive = more freezes than expected

    hd_s = _f(row, "highDangerShots")
    hd_g = _f(row, "highDangerGoals")
    hd_xg = _f(row, "highDangerxGoals")
    md_s = _f(row, "mediumDangerShots")
    md_g = _f(row, "mediumDangerGoals")
    md_xg = _f(row, "mediumDangerxGoals")
    ld_s = _f(row, "lowDangerShots")
    ld_g = _f(row, "lowDangerGoals")
    ld_xg = _f(row, "lowDangerxGoals")

    hd_sv = _danger_sv(hd_s, hd_g)
    md_sv = _danger_sv(md_s, md_g)
    ld_sv = _danger_sv(ld_s, ld_g)

    min_toi = 3600.0 if row.get("situation") in ("all", "5on5") else 600.0
    qual = [p for p in peers if _f(p, "icetime") >= min_toi]
    if len(qual) < 10:
        qual = peers

    def _p(
        val: float | None,
        fn: Callable[[dict[str, str]], float | None],
        higher: bool = True,
    ) -> str | None:
        return _pctile_badge(val, qual, fn, higher)

    gsax60_pop = [
        _per60(_f(p, "xGoals") - _f(p, "goals"), _f(p, "icetime")) for p in qual
    ]
    hd_pop = [
        (_f(p, "highDangerShots") - _f(p, "highDangerGoals")) / _f(p, "highDangerShots")
        for p in qual
        if _f(p, "highDangerShots") > 0
    ]
    md_pop = [
        (_f(p, "mediumDangerShots") - _f(p, "mediumDangerGoals"))
        / _f(p, "mediumDangerShots")
        for p in qual
        if _f(p, "mediumDangerShots") > 0
    ]
    ld_pop = [
        (_f(p, "lowDangerShots") - _f(p, "lowDangerGoals")) / _f(p, "lowDangerShots")
        for p in qual
        if _f(p, "lowDangerShots") > 0
    ]
    reb_pop = [
        _per60(_f(p, "xRebounds") - _f(p, "rebounds"), _f(p, "icetime")) for p in qual
    ]
    frz_pop = [
        _per60(_f(p, "freeze") - _f(p, "xFreeze"), _f(p, "icetime")) for p in qual
    ]

    radar = [
        {
            "axis": "GSAx / 60",
            "percentile": _percentile(gsax_60, gsax60_pop, True),
            "display": f"{gsax_60:+.2f}",
        },
        {
            "axis": "High-Danger",
            "percentile": _percentile(hd_sv, hd_pop, True) if hd_sv is not None else 50,
            "display": _fmt_sv_pct(hd_sv),
        },
        {
            "axis": "Med-Danger",
            "percentile": _percentile(md_sv, md_pop, True) if md_sv is not None else 50,
            "display": _fmt_sv_pct(md_sv),
        },
        {
            "axis": "Low-Danger",
            "percentile": _percentile(ld_sv, ld_pop, True) if ld_sv is not None else 50,
            "display": _fmt_sv_pct(ld_sv),
        },
        {
            "axis": "Rebound Ctrl",
            "percentile": _percentile(_per60(reb_diff, toi), reb_pop, True),
            "display": f"{reb_diff:+.1f} vs Exp",
        },
        {
            "axis": "Puck Freezes",
            "percentile": _percentile(_per60(frz_diff, toi), frz_pop, True),
            "display": f"{frz_diff:+.1f} vs Exp",
        },
    ]

    danger_bars = [
        {
            "zone": "Low Danger",
            "shots": int(round(ld_s)),
            "expected": round(ld_xg, 2),
            "actual": int(round(ld_g)),
        },
        {
            "zone": "Medium Danger",
            "shots": int(round(md_s)),
            "expected": round(md_xg, 2),
            "actual": int(round(md_g)),
        },
        {
            "zone": "High Danger",
            "shots": int(round(hd_s)),
            "expected": round(hd_xg, 2),
            "actual": int(round(hd_g)),
        },
    ]

    stat_groups = [
        {
            "title": "Goals Saved Above Expected & xG Profile",
            "items": [
                {
                    "label": "GSAx",
                    "value": f"{gsax:+.2f}",
                    "rank": _p(gsax, lambda r: _f(r, "xGoals") - _f(r, "goals")),
                    "highlight": True,
                },
                {
                    "label": "GSAx / 60",
                    "value": f"{gsax_60:+.2f}",
                    "rank": _p(
                        gsax_60,
                        lambda r: _per60(
                            _f(r, "xGoals") - _f(r, "goals"), _f(r, "icetime")
                        ),
                    ),
                    "highlight": gsax_60 > 0,
                },
                {
                    "label": "Flurry-Adj GSAx",
                    "value": f"{flurry_gsax:+.2f}",
                    "rank": _p(
                        flurry_gsax,
                        lambda r: _f(r, "flurryAdjustedxGoals") - _f(r, "goals"),
                    ),
                },
                {
                    "label": "Expected GA (xGA)",
                    "value": f"{xga:.2f}",
                    "rank": _p(xga, lambda r: _f(r, "xGoals"), False),
                },
                {
                    "label": "Actual GA",
                    "value": str(int(round(ga))),
                    "rank": _p(ga, lambda r: _f(r, "goals"), False),
                },
                {
                    "label": "xG / Shot Faced",
                    "value": f"{xg_per_shot:.3f}" if xg_per_shot is not None else "—",
                    "rank": _p(
                        xg_per_shot,
                        lambda r: (
                            (_f(r, "xGoals") / _f(r, "ongoal"))
                            if _f(r, "ongoal") > 0
                            else None
                        ),
                        False,
                    ),
                },
                {
                    "label": "Actual SV% (SOG)",
                    "value": _fmt_sv_pct(act_sv_sog),
                    "rank": _p(
                        act_sv_sog,
                        lambda r: (
                            ((_f(r, "ongoal") - _f(r, "goals")) / _f(r, "ongoal"))
                            if _f(r, "ongoal") > 0
                            else None
                        ),
                    ),
                },
                {
                    "label": "Expected SV% (SOG)",
                    "value": _fmt_sv_pct(exp_sv_sog),
                    "rank": _p(
                        exp_sv_sog,
                        lambda r: (
                            ((_f(r, "ongoal") - _f(r, "xGoals")) / _f(r, "ongoal"))
                            if _f(r, "ongoal") > 0
                            else None
                        ),
                    ),
                },
                {
                    "label": "Unblocked SV%",
                    "value": _fmt_sv_pct(act_unblocked_sv),
                    "rank": _p(
                        act_unblocked_sv,
                        lambda r: (
                            (
                                (_f(r, "unblocked_shot_attempts") - _f(r, "goals"))
                                / _f(r, "unblocked_shot_attempts")
                            )
                            if _f(r, "unblocked_shot_attempts") > 0
                            else None
                        ),
                    ),
                },
                {
                    "label": "Exp. Unblocked SV%",
                    "value": _fmt_sv_pct(exp_unblocked_sv),
                    "rank": _p(
                        exp_unblocked_sv,
                        lambda r: (
                            (
                                (_f(r, "unblocked_shot_attempts") - _f(r, "xGoals"))
                                / _f(r, "unblocked_shot_attempts")
                            )
                            if _f(r, "unblocked_shot_attempts") > 0
                            else None
                        ),
                    ),
                },
                {
                    "label": "Expected On-Goal",
                    "value": f"{x_on_goal:.1f}",
                    "rank": _p(x_on_goal, lambda r: _f(r, "xOnGoal")),
                },
                {
                    "label": "Blocked In Front",
                    "value": str(_i(row, "blocked_shot_attempts")),
                    "rank": _p(
                        _f(row, "blocked_shot_attempts"),
                        lambda r: _f(r, "blocked_shot_attempts"),
                    ),
                },
            ],
        },
        {
            "title": "Danger Splits, Rebounds & Puck Control",
            "items": [
                {
                    "label": "High-Danger GSAx",
                    "value": f"{(hd_xg - hd_g):+.2f}",
                    "rank": _p(
                        hd_xg - hd_g,
                        lambda r: _f(r, "highDangerxGoals") - _f(r, "highDangerGoals"),
                    ),
                    "highlight": True,
                },
                {
                    "label": "HD Unblocked SV%",
                    "value": _fmt_sv_pct(hd_sv),
                    "rank": _p(
                        hd_sv,
                        lambda r: _danger_sv(
                            _f(r, "highDangerShots"), _f(r, "highDangerGoals")
                        ),
                    ),
                },
                {
                    "label": "Med-Danger GSAx",
                    "value": f"{(md_xg - md_g):+.2f}",
                    "rank": _p(
                        md_xg - md_g,
                        lambda r: (
                            _f(r, "mediumDangerxGoals") - _f(r, "mediumDangerGoals")
                        ),
                    ),
                },
                {
                    "label": "MD Unblocked SV%",
                    "value": _fmt_sv_pct(md_sv),
                    "rank": _p(
                        md_sv,
                        lambda r: _danger_sv(
                            _f(r, "mediumDangerShots"), _f(r, "mediumDangerGoals")
                        ),
                    ),
                },
                {
                    "label": "Low-Danger GSAx",
                    "value": f"{(ld_xg - ld_g):+.2f}",
                    "rank": _p(
                        ld_xg - ld_g,
                        lambda r: _f(r, "lowDangerxGoals") - _f(r, "lowDangerGoals"),
                    ),
                },
                {
                    "label": "LD Unblocked SV%",
                    "value": _fmt_sv_pct(ld_sv),
                    "rank": _p(
                        ld_sv,
                        lambda r: _danger_sv(
                            _f(r, "lowDangerShots"), _f(r, "lowDangerGoals")
                        ),
                    ),
                },
                {
                    "label": "Rebounds Allowed",
                    "value": str(int(round(reb))),
                    "rank": _p(reb, lambda r: _f(r, "rebounds"), False),
                },
                {
                    "label": "Expected Rebounds",
                    "value": f"{x_reb:.1f}",
                    "rank": _p(x_reb, lambda r: _f(r, "xRebounds"), False),
                },
                {
                    "label": "Rebound Control",
                    "value": f"{reb_diff:+.1f}",
                    "rank": _p(
                        reb_diff, lambda r: _f(r, "xRebounds") - _f(r, "rebounds")
                    ),
                    "highlight": reb_diff > 0,
                },
                {
                    "label": "Puck Freezes",
                    "value": str(int(round(frz))),
                    "rank": _p(frz, lambda r: _f(r, "freeze")),
                },
                {
                    "label": "Expected Freezes",
                    "value": f"{x_frz:.1f}",
                    "rank": _p(x_frz, lambda r: _f(r, "xFreeze")),
                },
                {
                    "label": "Play Cont. In-Zone",
                    "value": str(_i(row, "playContinuedInZone")),
                    "rank": _p(
                        _f(row, "playContinuedInZone"),
                        lambda r: _f(r, "playContinuedInZone"),
                        False,
                    ),
                },
            ],
        },
    ]

    return {
        "statGroups": stat_groups,
        "charts": {
            "radar": radar,
            "dangerBars": danger_bars,
            "onOffImpact": [],
            "shiftStarts": [],
            "expectedVsActual": [
                {
                    "label": "Overall Goaltending",
                    "expected": round(xga, 2),
                    "actual": round(ga, 2),
                    "delta": round(gsax, 2),
                    "deltaLabel": "GSAx",
                },
                {
                    "label": "High-Danger Shots",
                    "expected": round(hd_xg, 2),
                    "actual": round(hd_g, 2),
                    "delta": round(hd_xg - hd_g, 2),
                    "deltaLabel": "HD GSAx",
                },
                {
                    "label": "Medium-Danger Shots",
                    "expected": round(md_xg, 2),
                    "actual": round(md_g, 2),
                    "delta": round(md_xg - md_g, 2),
                    "deltaLabel": "MD GSAx",
                },
            ],
        },
        "backfill": {
            "savePct": _fmt_sv_pct(act_sv_sog),
            "shotsAgainst": str(int(round(sog))),
            "goalsAgainst": str(int(round(ga))),
            "timeOnIce": toi,
        },
        "backfillRanks": {
            "savePct": _p(
                act_sv_sog,
                lambda r: (
                    ((_f(r, "ongoal") - _f(r, "goals")) / _f(r, "ongoal"))
                    if _f(r, "ongoal") > 0
                    else None
                ),
            ),
            "shotsAgainst": _p(sog, lambda r: _f(r, "ongoal")),
            "goalsAgainst": _p(ga, lambda r: _f(r, "goals"), False),
            "timeOnIce": _p(toi, lambda r: _f(r, "icetime")),
        },
    }


def get_goalie_moneypuck(player_id: int, season_id: str) -> dict[str, Any] | None:
    rows = _load_dataset("goalies", season_id)
    if not rows:
        return None

    pid_str = str(player_id)
    by_sit: dict[str, dict[str, str]] = {}
    peers_by_sit: dict[str, list[dict[str, str]]] = {s: [] for s in SITUATIONS}

    for r in rows:
        sit = r.get("situation", "")
        if sit in peers_by_sit:
            peers_by_sit[sit].append(r)
        if r.get("playerId") == pid_str and sit in SITUATIONS:
            by_sit[sit] = r

    if not by_sit:
        return None

    situations_out = {
        sit: _build_goalie_situation(by_sit[sit], peers_by_sit[sit])
        for sit in SITUATIONS
        if sit in by_sit
    }
    return {
        "source": "MoneyPuck.com",
        "defaultSituation": "all"
        if "all" in situations_out
        else next(iter(situations_out)),
        "situations": situations_out,
    }


# ==============================================================================
# TEAM ANALYTICS
# ==============================================================================


def _build_team_situation(
    row: dict[str, str], peers: list[dict[str, str]]
) -> dict[str, Any]:
    toi = _f(row, "iceTime")
    gp = max(1, _i(row, "games_played", 1))
    xgf = _f(row, "xGoalsFor")
    xga = _f(row, "xGoalsAgainst")
    xg_diff = xgf - xga
    xgf_pg = xgf / gp
    xg_pct = _f(row, "xGoalsPercentage")
    cf_pct = _f(row, "corsiPercentage")
    ff_pct = _f(row, "fenwickPercentage")

    flurry_f = _f(row, "flurryAdjustedxGoalsFor")
    flurry_a = _f(row, "flurryAdjustedxGoalsAgainst")
    flurry_pct = flurry_f / (flurry_f + flurry_a) if (flurry_f + flurry_a) > 0 else 0.5

    sv_f = _f(row, "scoreVenueAdjustedxGoalsFor")
    sv_a = _f(row, "scoreVenueAdjustedxGoalsAgainst")
    sv_pct = sv_f / (sv_f + sv_a) if (sv_f + sv_a) > 0 else 0.5

    gf = _f(row, "goalsFor")
    ga = _f(row, "goalsAgainst")
    g_above_exp = gf - xgf
    gsax_team = xga - ga

    xgf_60 = _per60(xgf, toi)
    xga_60 = _per60(xga, toi)

    hd_xgf = _f(row, "highDangerxGoalsFor")
    hd_xga = _f(row, "highDangerxGoalsAgainst")
    hd_xg_pct = hd_xgf / (hd_xgf + hd_xga) if (hd_xgf + hd_xga) > 0 else 0.5

    sa_cf = _f(row, "scoreAdjustedShotsAttemptsFor")
    sa_ca = _f(row, "scoreAdjustedShotsAttemptsAgainst")
    sa_cf_pct = sa_cf / (sa_cf + sa_ca) if (sa_cf + sa_ca) > 0 else None

    sa_ff = _f(row, "scoreAdjustedUnblockedShotAttemptsFor")
    sa_fa = _f(row, "scoreAdjustedUnblockedShotAttemptsAgainst")
    sa_ff_pct = sa_ff / (sa_ff + sa_fa) if (sa_ff + sa_fa) > 0 else None

    sog_f = _f(row, "shotsOnGoalFor")
    sog_a = _f(row, "shotsOnGoalAgainst")
    sh_pct = (gf / sog_f) if sog_f > 0 else None
    sv_rate = (1.0 - (ga / sog_a)) if sog_a > 0 else None

    def _rk(
        val: float | None,
        fn: Callable[[dict[str, str]], float | None],
        higher: bool = True,
    ) -> str | None:
        return _team_rank_badge(val, peers, fn, higher)

    def _ratio_fn(f_key: str, a_key: str) -> Callable[[dict[str, str]], float | None]:
        def _inner(r: dict[str, str]) -> float | None:
            fv, av = _f(r, f_key), _f(r, a_key)
            return fv / (fv + av) if (fv + av) > 0 else None

        return _inner

    def _sh_fn(r: dict[str, str]) -> float | None:
        sog = _f(r, "shotsOnGoalFor")
        return (_f(r, "goalsFor") / sog) if sog > 0 else None

    def _sv_fn(r: dict[str, str]) -> float | None:
        sog = _f(r, "shotsOnGoalAgainst")
        return (1.0 - (_f(r, "goalsAgainst") / sog)) if sog > 0 else None

    def _pdo_fn(r: dict[str, str]) -> float | None:
        sh, sv = _sh_fn(r), _sv_fn(r)
        return (sh + sv) * 100.0 if sh is not None and sv is not None else None

    # League-wide populations (32 NHL teams) for radar percentiles
    xgf60_pop = [_per60(_f(p, "xGoalsFor"), _f(p, "iceTime")) for p in peers]
    xga60_pop = [_per60(_f(p, "xGoalsAgainst"), _f(p, "iceTime")) for p in peers]
    cf_pop = [_f(p, "corsiPercentage") for p in peers]
    fin_pop = [_f(p, "goalsFor") - _f(p, "xGoalsFor") for p in peers]
    gsax_pop = [_f(p, "xGoalsAgainst") - _f(p, "goalsAgainst") for p in peers]
    hd_pct_pop = [
        _f(p, "highDangerxGoalsFor")
        / (_f(p, "highDangerxGoalsFor") + _f(p, "highDangerxGoalsAgainst"))
        for p in peers
        if (_f(p, "highDangerxGoalsFor") + _f(p, "highDangerxGoalsAgainst")) > 0
    ]

    radar = [
        {
            "axis": "Offense (xGF/60)",
            "percentile": _percentile(xgf_60, xgf60_pop, True),
            "display": f"{xgf_60:.2f} (#{_rank_in_list(xgf_60, xgf60_pop, True)})",
        },
        {
            "axis": "Defense (xGA/60)",
            "percentile": _percentile(xga_60, xga60_pop, False),
            "display": f"{xga_60:.2f} (#{_rank_in_list(xga_60, xga60_pop, False)})",
        },
        {
            "axis": "Possession (CF%)",
            "percentile": _percentile(cf_pct, cf_pop, True),
            "display": f"{_fmt_pct(cf_pct)} (#{_rank_in_list(cf_pct, cf_pop, True)})",
        },
        {
            "axis": "Finishing",
            "percentile": _percentile(g_above_exp, fin_pop, True),
            "display": f"{g_above_exp:+.1f} G-xG",
        },
        {
            "axis": "Goaltending",
            "percentile": _percentile(gsax_team, gsax_pop, True),
            "display": f"{gsax_team:+.1f} GSAx",
        },
        {
            "axis": "High-Danger %",
            "percentile": _percentile(hd_xg_pct, hd_pct_pop, True),
            "display": _fmt_pct(hd_xg_pct),
        },
    ]

    danger_comparison = [
        {
            "zone": "Low Danger",
            "shotsFor": _i(row, "lowDangerShotsFor"),
            "shotsAgainst": _i(row, "lowDangerShotsAgainst"),
            "xGF": round(_f(row, "lowDangerxGoalsFor"), 2),
            "xGA": round(_f(row, "lowDangerxGoalsAgainst"), 2),
            "goalsFor": _i(row, "lowDangerGoalsFor"),
            "goalsAgainst": _i(row, "lowDangerGoalsAgainst"),
        },
        {
            "zone": "Medium Danger",
            "shotsFor": _i(row, "mediumDangerShotsFor"),
            "shotsAgainst": _i(row, "mediumDangerShotsAgainst"),
            "xGF": round(_f(row, "mediumDangerxGoalsFor"), 2),
            "xGA": round(_f(row, "mediumDangerxGoalsAgainst"), 2),
            "goalsFor": _i(row, "mediumDangerGoalsFor"),
            "goalsAgainst": _i(row, "mediumDangerGoalsAgainst"),
        },
        {
            "zone": "High Danger",
            "shotsFor": _i(row, "highDangerShotsFor"),
            "shotsAgainst": _i(row, "highDangerShotsAgainst"),
            "xGF": round(_f(row, "highDangerxGoalsFor"), 2),
            "xGA": round(_f(row, "highDangerxGoalsAgainst"), 2),
            "goalsFor": _i(row, "highDangerGoalsFor"),
            "goalsAgainst": _i(row, "highDangerGoalsAgainst"),
        },
    ]

    stat_groups = [
        {
            "title": "Expected Goals & Dominance",
            "items": [
                {
                    "label": "Expected Goals %",
                    "value": _fmt_pct(xg_pct),
                    "rank": _rk(xg_pct, lambda r: _f(r, "xGoalsPercentage")),
                    "highlight": True,
                },
                {
                    "label": "Flurry-Adj xG %",
                    "value": _fmt_pct(flurry_pct),
                    "rank": _rk(
                        flurry_pct,
                        _ratio_fn(
                            "flurryAdjustedxGoalsFor", "flurryAdjustedxGoalsAgainst"
                        ),
                    ),
                },
                {
                    "label": "Score/Venue-Adj xG %",
                    "value": _fmt_pct(sv_pct),
                    "rank": _rk(
                        sv_pct,
                        _ratio_fn(
                            "scoreVenueAdjustedxGoalsFor",
                            "scoreVenueAdjustedxGoalsAgainst",
                        ),
                    ),
                },
                {
                    "label": "xGoals For",
                    "value": f"{xgf:.2f}",
                    "rank": _rk(xgf, lambda r: _f(r, "xGoalsFor")),
                },
                {
                    "label": "xGoals Against",
                    "value": f"{xga:.2f}",
                    "rank": _rk(xga, lambda r: _f(r, "xGoalsAgainst"), False),
                },
                {
                    "label": "xGoal Diff",
                    "value": f"{xg_diff:+.2f}",
                    "rank": _rk(
                        xg_diff, lambda r: _f(r, "xGoalsFor") - _f(r, "xGoalsAgainst")
                    ),
                    "highlight": xg_diff > 0,
                },
                {
                    "label": "xGF / 60",
                    "value": f"{xgf_60:.2f}",
                    "rank": _rk(
                        xgf_60, lambda r: _per60(_f(r, "xGoalsFor"), _f(r, "iceTime"))
                    ),
                },
                {
                    "label": "xGA / 60",
                    "value": f"{xga_60:.2f}",
                    "rank": _rk(
                        xga_60,
                        lambda r: _per60(_f(r, "xGoalsAgainst"), _f(r, "iceTime")),
                        False,
                    ),
                },
                {
                    "label": "Finishing (GF − xGF)",
                    "value": f"{g_above_exp:+.2f}",
                    "rank": _rk(
                        g_above_exp, lambda r: _f(r, "goalsFor") - _f(r, "xGoalsFor")
                    ),
                },
                {
                    "label": "Team GSAx (xGA − GA)",
                    "value": f"{gsax_team:+.2f}",
                    "rank": _rk(
                        gsax_team,
                        lambda r: _f(r, "xGoalsAgainst") - _f(r, "goalsAgainst"),
                    ),
                    "highlight": gsax_team > 0,
                },
                {
                    "label": "Shot Credit For",
                    "value": f"{_f(row, 'totalShotCreditFor'):.2f}",
                    "rank": _rk(
                        _f(row, "totalShotCreditFor"),
                        lambda r: _f(r, "totalShotCreditFor"),
                    ),
                },
                {
                    "label": "Shot Credit Against",
                    "value": f"{_f(row, 'totalShotCreditAgainst'):.2f}",
                    "rank": _rk(
                        _f(row, "totalShotCreditAgainst"),
                        lambda r: _f(r, "totalShotCreditAgainst"),
                        False,
                    ),
                },
            ],
        },
        {
            "title": "Shot Quality, Rebounds & Control",
            "items": [
                {
                    "label": "High-Danger xG %",
                    "value": _fmt_pct(hd_xg_pct),
                    "rank": _rk(
                        hd_xg_pct,
                        _ratio_fn("highDangerxGoalsFor", "highDangerxGoalsAgainst"),
                    ),
                    "highlight": True,
                },
                {
                    "label": "HD Shots For / Agst",
                    "value": f"{_i(row, 'highDangerShotsFor')} / {_i(row, 'highDangerShotsAgainst')}",
                    "rank": _rk(
                        _f(row, "highDangerShotsFor")
                        - _f(row, "highDangerShotsAgainst"),
                        lambda r: (
                            _f(r, "highDangerShotsFor")
                            - _f(r, "highDangerShotsAgainst")
                        ),
                    ),
                },
                {
                    "label": "HD xG For / Agst",
                    "value": f"{hd_xgf:.1f} / {hd_xga:.1f}",
                    "rank": _rk(
                        hd_xgf - hd_xga,
                        lambda r: (
                            _f(r, "highDangerxGoalsFor")
                            - _f(r, "highDangerxGoalsAgainst")
                        ),
                    ),
                },
                {
                    "label": "HD Goals For / Agst",
                    "value": f"{_i(row, 'highDangerGoalsFor')} / {_i(row, 'highDangerGoalsAgainst')}",
                    "rank": _rk(
                        _f(row, "highDangerGoalsFor")
                        - _f(row, "highDangerGoalsAgainst"),
                        lambda r: (
                            _f(r, "highDangerGoalsFor")
                            - _f(r, "highDangerGoalsAgainst")
                        ),
                    ),
                },
                {
                    "label": "MD xG For / Agst",
                    "value": f"{_f(row, 'mediumDangerxGoalsFor'):.1f} / {_f(row, 'mediumDangerxGoalsAgainst'):.1f}",
                    "rank": _rk(
                        _f(row, "mediumDangerxGoalsFor")
                        - _f(row, "mediumDangerxGoalsAgainst"),
                        lambda r: (
                            _f(r, "mediumDangerxGoalsFor")
                            - _f(r, "mediumDangerxGoalsAgainst")
                        ),
                    ),
                },
                {
                    "label": "LD xG For / Agst",
                    "value": f"{_f(row, 'lowDangerxGoalsFor'):.1f} / {_f(row, 'lowDangerxGoalsAgainst'):.1f}",
                    "rank": _rk(
                        _f(row, "lowDangerxGoalsFor")
                        - _f(row, "lowDangerxGoalsAgainst"),
                        lambda r: (
                            _f(r, "lowDangerxGoalsFor")
                            - _f(r, "lowDangerxGoalsAgainst")
                        ),
                    ),
                },
                {
                    "label": "Rebounds For / Agst",
                    "value": f"{_i(row, 'reboundsFor')} / {_i(row, 'reboundsAgainst')}",
                    "rank": _rk(
                        _f(row, "reboundsFor") - _f(row, "reboundsAgainst"),
                        lambda r: _f(r, "reboundsFor") - _f(r, "reboundsAgainst"),
                    ),
                },
                {
                    "label": "Rebound Goals F / A",
                    "value": f"{_i(row, 'reboundGoalsFor')} / {_i(row, 'reboundGoalsAgainst')}",
                    "rank": _rk(
                        _f(row, "reboundGoalsFor") - _f(row, "reboundGoalsAgainst"),
                        lambda r: (
                            _f(r, "reboundGoalsFor") - _f(r, "reboundGoalsAgainst")
                        ),
                    ),
                },
                {
                    "label": "Rebound xG F / A",
                    "value": f"{_f(row, 'reboundxGoalsFor'):.1f} / {_f(row, 'reboundxGoalsAgainst'):.1f}",
                    "rank": _rk(
                        _f(row, "reboundxGoalsFor") - _f(row, "reboundxGoalsAgainst"),
                        lambda r: (
                            _f(r, "reboundxGoalsFor") - _f(r, "reboundxGoalsAgainst")
                        ),
                    ),
                },
                {
                    "label": "D-Zone Giveaways F/A",
                    "value": f"{_i(row, 'dZoneGiveawaysFor')} / {_i(row, 'dZoneGiveawaysAgainst')}",
                    "rank": _rk(
                        _f(row, "dZoneGiveawaysAgainst") - _f(row, "dZoneGiveawaysFor"),
                        lambda r: (
                            _f(r, "dZoneGiveawaysAgainst") - _f(r, "dZoneGiveawaysFor")
                        ),
                    ),
                },
                {
                    "label": "Score-Adj Corsi %",
                    "value": _fmt_pct(sa_cf_pct),
                    "rank": _rk(
                        sa_cf_pct,
                        _ratio_fn(
                            "scoreAdjustedShotsAttemptsFor",
                            "scoreAdjustedShotsAttemptsAgainst",
                        ),
                    ),
                },
                {
                    "label": "Score-Adj Fenwick %",
                    "value": _fmt_pct(sa_ff_pct),
                    "rank": _rk(
                        sa_ff_pct,
                        _ratio_fn(
                            "scoreAdjustedUnblockedShotAttemptsFor",
                            "scoreAdjustedUnblockedShotAttemptsAgainst",
                        ),
                    ),
                },
            ],
        },
    ]

    pdo_num = (
        (sh_pct + sv_rate) * 100.0
        if sh_pct is not None and sv_rate is not None
        else None
    )

    return {
        "statGroups": stat_groups,
        "charts": {
            "radar": radar,
            "dangerComparison": danger_comparison,
            "expectedVsActual": [
                {
                    "label": "Team Offense",
                    "expected": round(xgf, 2),
                    "actual": round(gf, 2),
                    "delta": round(g_above_exp, 2),
                    "deltaLabel": "GF − xGF",
                },
                {
                    "label": "Team Defense / Goalies",
                    "expected": round(xga, 2),
                    "actual": round(ga, 2),
                    "delta": round(gsax_team, 2),
                    "deltaLabel": "GSAx",
                },
            ],
        },
        "summaryShares": {
            "xgPct": round(xg_pct * 100.0, 1),
            "corsiPct": round(cf_pct * 100.0, 1),
            "fenwickPct": round(ff_pct * 100.0, 1),
        },
        "backfill": {
            "satPct": _fmt_pct(cf_pct),
            "usatPct": _fmt_pct(ff_pct),
            "satPctClose": _fmt_pct(sa_cf_pct),
            "satFor": str(_i(row, "shotAttemptsFor")),
            "satAgainst": str(_i(row, "shotAttemptsAgainst")),
            "satTotal": str(
                _i(row, "shotAttemptsFor") + _i(row, "shotAttemptsAgainst")
            ),
            "shPct5v5": _fmt_pct(sh_pct),
            "svPct5v5": _fmt_sv_pct(sv_rate),
            "pdo": f"{pdo_num:.1f}" if pdo_num is not None else None,
            "goalsFor": str(int(round(gf))),
            "goalsAgainst": str(int(round(ga))),
            "missedShots": str(_i(row, "missedShotsFor")),
            "giveaways": str(_i(row, "giveawaysFor")),
            "giveawaysPer60": f"{_per60(_f(row, 'giveawaysFor'), toi):.1f}",
            "blockedShots": str(_i(row, "blockedShotAttemptsAgainst")),
            "blocksPer60": f"{_per60(_f(row, 'blockedShotAttemptsAgainst'), toi):.1f}",
            "takeaways": str(_i(row, "takeawaysFor")),
            "takeawaysPer60": f"{_per60(_f(row, 'takeawaysFor'), toi):.1f}",
            "hits": str(_i(row, "hitsFor")),
            "hitsPer60": f"{_per60(_f(row, 'hitsFor'), toi):.1f}",
            "pim": str(_i(row, "penalityMinutesFor")),
            "penaltiesTaken": str(_i(row, "penaltiesFor")),
            "penaltiesDrawn": str(_i(row, "penaltiesAgainst")),
            "netPenalties": f"{(_i(row, 'penaltiesAgainst') - _i(row, 'penaltiesFor')):+d}",
            "xgfPerGame": f"{xgf_pg:.2f}",
            "pimDrawn": str(_i(row, "penalityMinutesAgainst")),
        },
        "backfillRanks": {
            "satPct": _rk(cf_pct, lambda r: _f(r, "corsiPercentage")),
            "usatPct": _rk(ff_pct, lambda r: _f(r, "fenwickPercentage")),
            "satPctClose": _rk(
                sa_cf_pct,
                _ratio_fn(
                    "scoreAdjustedShotsAttemptsFor", "scoreAdjustedShotsAttemptsAgainst"
                ),
            ),
            "satFor": _rk(
                _f(row, "shotAttemptsFor"), lambda r: _f(r, "shotAttemptsFor")
            ),
            "satAgainst": _rk(
                _f(row, "shotAttemptsAgainst"),
                lambda r: _f(r, "shotAttemptsAgainst"),
                False,
            ),
            "satTotal": _rk(
                _f(row, "shotAttemptsFor") + _f(row, "shotAttemptsAgainst"),
                lambda r: _f(r, "shotAttemptsFor") + _f(r, "shotAttemptsAgainst"),
            ),
            "shPct5v5": _rk(sh_pct, _sh_fn),
            "svPct5v5": _rk(sv_rate, _sv_fn),
            "pdo": _rk(pdo_num, _pdo_fn),
            "goalsFor": _rk(gf, lambda r: _f(r, "goalsFor")),
            "goalsAgainst": _rk(ga, lambda r: _f(r, "goalsAgainst"), False),
            "missedShots": _rk(
                _f(row, "missedShotsFor"), lambda r: _f(r, "missedShotsFor")
            ),
            "giveaways": _rk(
                _f(row, "giveawaysFor"), lambda r: _f(r, "giveawaysFor"), False
            ),
            "giveawaysPer60": _rk(
                _per60(_f(row, "giveawaysFor"), toi),
                lambda r: _per60(_f(r, "giveawaysFor"), _f(r, "iceTime")),
                False,
            ),
            "blockedShots": _rk(
                _f(row, "blockedShotAttemptsAgainst"),
                lambda r: _f(r, "blockedShotAttemptsAgainst"),
            ),
            "blocksPer60": _rk(
                _per60(_f(row, "blockedShotAttemptsAgainst"), toi),
                lambda r: _per60(_f(r, "blockedShotAttemptsAgainst"), _f(r, "iceTime")),
            ),
            "takeaways": _rk(_f(row, "takeawaysFor"), lambda r: _f(r, "takeawaysFor")),
            "takeawaysPer60": _rk(
                _per60(_f(row, "takeawaysFor"), toi),
                lambda r: _per60(_f(r, "takeawaysFor"), _f(r, "iceTime")),
            ),
            "hits": _rk(_f(row, "hitsFor"), lambda r: _f(r, "hitsFor")),
            "hitsPer60": _rk(
                _per60(_f(row, "hitsFor"), toi),
                lambda r: _per60(_f(r, "hitsFor"), _f(r, "iceTime")),
            ),
            "pim": _rk(
                _f(row, "penalityMinutesFor"),
                lambda r: _f(r, "penalityMinutesFor"),
                False,
            ),
            "penaltiesTaken": _rk(
                _f(row, "penaltiesFor"), lambda r: _f(r, "penaltiesFor"), False
            ),
            "penaltiesDrawn": _rk(
                _f(row, "penaltiesAgainst"), lambda r: _f(r, "penaltiesAgainst")
            ),
            "netPenalties": _rk(
                _f(row, "penaltiesAgainst") - _f(row, "penaltiesFor"),
                lambda r: _f(r, "penaltiesAgainst") - _f(r, "penaltiesFor"),
            ),
            "xgfPerGame": _rk(
                xgf_pg,
                lambda r: _f(r, "xGoalsFor") / max(1.0, _f(r, "games_played", 1.0)),
            ),
            "pimDrawn": _rk(
                _f(row, "penalityMinutesAgainst"),
                lambda r: _f(r, "penalityMinutesAgainst"),
            ),
        },
    }


def get_team_moneypuck(team_abbrev: str, season_id: str) -> dict[str, Any] | None:
    rows = _load_dataset("teams", season_id)
    if not rows:
        return None

    code = team_abbrev.strip().upper()
    by_sit: dict[str, dict[str, str]] = {}
    peers_by_sit: dict[str, list[dict[str, str]]] = {s: [] for s in SITUATIONS}

    for r in rows:
        sit = r.get("situation", "")
        if sit in peers_by_sit:
            peers_by_sit[sit].append(r)
        if str(r.get("team", "")).upper() == code and sit in SITUATIONS:
            by_sit[sit] = r

    if not by_sit:
        return None

    situations_out = {
        sit: _build_team_situation(by_sit[sit], peers_by_sit[sit])
        for sit in SITUATIONS
        if sit in by_sit
    }

    sit_labels = {
        "5on5": "5v5",
        "all": "All",
        "5on4": "5v4 PP",
        "4on5": "4v5 PK",
    }
    situational_dominance = [
        {
            "situation": sit_labels[sit],
            **situations_out[sit]["summaryShares"],
        }
        for sit in SITUATIONS
        if sit in situations_out
    ]

    return {
        "source": "MoneyPuck.com",
        "defaultSituation": "5on5"
        if "5on5" in situations_out
        else next(iter(situations_out)),
        "situations": situations_out,
        "situationalDominance": situational_dominance,
    }
