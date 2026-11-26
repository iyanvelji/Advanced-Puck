import { useEffect, useMemo, useState } from "react";
import { fetchTeamProfile } from "../api/teams";
import type {
  RosterPerson,
  TeamProfileResponse,
  TeamSkaterRow,
} from "../types/teams";
import PlayerAvatar from "./PlayerAvatar";
import TeamMoneyPuckSection from "./TeamMoneyPuckSection";

interface TeamDetailViewProps {
  teamAbbrev: string;
  onBack: () => void;
  onSelectPlayer: (playerId: number) => void;
}

type TeamTab = "overview" | "roster" | "schedule" | "prospects";
type SkaterSortKey =
  | "gp"
  | "goals"
  | "assists"
  | "points"
  | "plusMinus"
  | "ppGoals"
  | "gwg"
  | "shots"
  | "shootingPct"
  | "pim";

function formatLocalTime(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default function TeamDetailView({
  teamAbbrev,
  onBack,
  onSelectPlayer,
}: TeamDetailViewProps) {
  const [profile, setProfile] = useState<TeamProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<TeamTab>("overview");
  const [rosterSubView, setRosterSubView] = useState<"stats" | "bios">("stats");
  const [skaterSort, setSkaterSort] = useState<{
    key: SkaterSortKey;
    dir: "asc" | "desc";
  }>({ key: "points", dir: "desc" });

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");
    setActiveTab("overview");

    fetchTeamProfile(teamAbbrev)
      .then((res) => {
        if (!ignore) setProfile(res);
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(
            err instanceof Error ? err.message : "Failed to load team profile",
          );
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [teamAbbrev]);

  const sortedSkaters = useMemo(() => {
    const list: TeamSkaterRow[] = profile?.skaters ?? [];
    return [...list].sort((a, b) =>
      skaterSort.dir === "asc"
        ? a[skaterSort.key] - b[skaterSort.key]
        : b[skaterSort.key] - a[skaterSort.key],
    );
  }, [profile, skaterSort]);

  const toggleSkaterSort = (key: SkaterSortKey) => {
    setSkaterSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { key, dir: "desc" },
    );
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <button
          type="button"
          onClick={onBack}
          className="rounded-xl border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-300 transition hover:bg-sky-500/20"
        >
          ← Back to Standings
        </button>
        <div className="rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-14 text-center text-sm text-zinc-400">
          Loading {teamAbbrev} analytics, NHL EDGE tracking, roster, and
          schedule...
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="space-y-6">
        <button
          type="button"
          onClick={onBack}
          className="rounded-xl border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-300 transition hover:bg-sky-500/20"
        >
          ← Back to Standings
        </button>
        <div className="rounded-2xl border border-red-500/30 bg-red-950/20 p-6 text-sm text-red-200">
          {error || "Team profile unavailable."}
        </div>
      </div>
    );
  }

  const {
    header,
    headlineKpis,
    statGroups,
    periodScoring,
    edge,
    goalies,
    roster,
    recentGames,
    upcomingGames,
    prospects,
  } = profile;

  const totalProspects =
    prospects.forwards.length +
    prospects.defensemen.length +
    prospects.goalies.length;

  const maxPeriodGoals = Math.max(
    1,
    ...periodScoring.flatMap((p) => [p.gf, p.ga]),
  );

  return (
    <div className="space-y-6">
      {/* Top Bar */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="rounded-xl border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-300 transition hover:bg-sky-500/20"
        >
          ← Back to Standings
        </button>
        <span className="text-xs font-medium uppercase tracking-widest text-zinc-400">
          {profile.seasonLabel} Team Analytics
        </span>
      </div>

      {/* Team Hero Card */}
      <section className="relative overflow-hidden rounded-2xl border border-sky-500/25 bg-[#0b0f17] shadow-[0_18px_55px_rgba(0,0,0,0.75)]">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-sky-500/[0.11] via-transparent to-black/60" />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/70 to-transparent" />

        <div className="relative p-6 sm:p-8">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            {/* Identity */}
            <div className="flex items-center gap-5">
              <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-2xl border border-sky-400/40 bg-[#05070a]/90 p-3 shadow-[0_0_32px_rgba(56,189,248,0.22)] sm:h-28 sm:w-28">
                {header.teamLogo ? (
                  <img
                    src={header.teamLogo}
                    alt={header.teamName}
                    className="h-full w-full object-contain"
                  />
                ) : (
                  <span className="text-2xl font-extrabold text-sky-400">
                    {profile.teamAbbrev}
                  </span>
                )}
              </div>

              <div>
                <div className="flex flex-wrap items-center gap-2">
                  {header.divisionRank && header.divisionName && (
                    <span className="rounded-lg border border-sky-400/40 bg-sky-500/15 px-2.5 py-0.5 text-xs font-bold text-sky-300">
                      {header.divisionRank} {header.divisionName}
                    </span>
                  )}
                  {header.leagueRank && (
                    <span className="rounded-lg border border-white/10 bg-black/55 px-2.5 py-0.5 text-xs font-semibold text-zinc-200">
                      {header.leagueRank} NHL
                    </span>
                  )}
                  {header.conferenceName && (
                    <span className="rounded-lg border border-white/10 bg-black/55 px-2.5 py-0.5 text-xs text-zinc-400">
                      {header.conferenceName} Conference
                    </span>
                  )}
                </div>

                <h1 className="mt-2.5 text-2xl font-extrabold tracking-tight text-white sm:text-4xl">
                  {header.teamName}
                </h1>
                <p className="mt-1 text-xs uppercase tracking-[0.2em] text-sky-400/80">
                  {profile.seasonLabel} Regular Season
                </p>
              </div>
            </div>

            {/* Quick Splits Box */}
            <div className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-xl border border-white/10 bg-black/50 px-5 py-4 text-xs tabular-nums sm:grid-cols-4">
              <div>
                <p className="uppercase tracking-wider text-zinc-500">Home</p>
                <p className="mt-0.5 text-sm font-bold text-white">
                  {header.homeRecord}
                </p>
              </div>
              <div>
                <p className="uppercase tracking-wider text-zinc-500">Away</p>
                <p className="mt-0.5 text-sm font-bold text-white">
                  {header.awayRecord}
                </p>
              </div>
              <div>
                <p className="uppercase tracking-wider text-zinc-500">
                  Last 10
                </p>
                <p className="mt-0.5 text-sm font-bold text-white">
                  {header.l10}
                </p>
              </div>
              <div>
                <p className="uppercase tracking-wider text-zinc-500">Streak</p>
                <p className="mt-0.5 text-sm font-bold text-sky-400">
                  {header.streak}
                </p>
              </div>
            </div>
          </div>

          {/* 6 Headline KPI Cards */}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {headlineKpis.map((kpi) => (
              <div
                key={kpi.label}
                className={`rounded-xl border px-4 py-3.5 text-center tabular-nums ${
                  kpi.highlight
                    ? "border-sky-400/50 bg-sky-500/15 shadow-[0_0_24px_rgba(56,189,248,0.16)]"
                    : "border-white/10 bg-black/55"
                }`}
              >
                <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400">
                  {kpi.label}
                </p>
                <p
                  className={`mt-1 text-2xl font-extrabold ${
                    kpi.highlight
                      ? "text-sky-400 drop-shadow-[0_0_10px_rgba(56,189,248,0.45)]"
                      : "text-white"
                  }`}
                >
                  {kpi.value}
                </p>
                {kpi.rank && (
                  <p className="mt-0.5 text-[11px] font-medium text-sky-300/80">
                    {kpi.rank} in NHL
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Sub-Navigation Tabs */}
        <div className="relative grid grid-cols-2 border-t border-white/10 bg-black/45 sm:grid-cols-4">
          {(
            [
              ["overview", "Overview & Advanced"],
              [
                "roster",
                `Roster & Stats (${sortedSkaters.length + goalies.length})`,
              ],
              ["schedule", "Schedule & Results"],
              ["prospects", `Prospects (${totalProspects})`],
            ] as [TeamTab, string][]
          ).map(([tabKey, label]) => {
            const isActive = activeTab === tabKey;
            return (
              <button
                key={tabKey}
                type="button"
                onClick={() => setActiveTab(tabKey)}
                className={`relative py-3.5 text-center text-xs font-semibold transition sm:text-sm ${
                  isActive
                    ? "bg-sky-500/10 text-white"
                    : "text-zinc-400 hover:bg-white/[0.03] hover:text-zinc-200"
                }`}
              >
                {label}
                {isActive && (
                  <span className="absolute inset-x-0 bottom-0 h-0.5 bg-sky-400 shadow-[0_0_12px_#38bdf8]" />
                )}
              </button>
            );
          })}
        </div>
      </section>

      {/* TAB 1: OVERVIEW, ADVANCED ANALYTICS, PERIOD SCORING & NHL EDGE */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* 6 Categorized Stat Panels */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {statGroups.map((group) => (
              <section
                key={group.title}
                className="relative overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_12px_36px_rgba(0,0,0,0.65)]"
              >
                <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/50 to-transparent" />
                <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.1] via-transparent to-transparent px-5 py-3.5">
                  <h2 className="text-base font-bold tracking-tight text-white">
                    {group.title}
                  </h2>
                </div>
                <div className="grid grid-cols-2 gap-3 p-5 sm:grid-cols-3">
                  {group.items.map((item) => (
                    <div
                      key={item.label}
                      className="rounded-xl border border-white/5 bg-black/45 px-3.5 py-3 tabular-nums"
                    >
                      <div className="flex items-start justify-between gap-1">
                        <p className="text-[11px] text-zinc-400">
                          {item.label}
                        </p>
                        {item.rank && (
                          <span className="shrink-0 rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-300">
                            {item.rank}
                          </span>
                        )}
                      </div>
                      <p
                        className={`mt-1 text-lg font-bold ${
                          item.highlight
                            ? "text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.4)]"
                            : "text-white"
                        }`}
                      >
                        {item.value}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>

          {/* Period-by-Period Scoring Breakdown */}
          {periodScoring.length > 0 && (
            <section className="relative overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5 shadow-[0_12px_36px_rgba(0,0,0,0.65)]">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/50 to-transparent" />
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-bold text-white">
                  Period-by-Period Scoring
                </h2>
                <div className="flex items-center gap-4 text-xs text-zinc-400">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-sky-400" />
                    Goals For
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-zinc-500" />
                    Goals Against
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {periodScoring.map((p) => (
                  <div
                    key={p.period}
                    className="rounded-xl border border-white/10 bg-black/45 p-4 tabular-nums"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
                        {p.period}
                      </span>
                      <span
                        className={`text-xs font-bold ${
                          p.diff > 0
                            ? "text-sky-400"
                            : p.diff < 0
                              ? "text-zinc-400"
                              : "text-zinc-300"
                        }`}
                      >
                        {p.diff > 0 ? `+${p.diff}` : p.diff}
                      </span>
                    </div>

                    <div className="mt-3 space-y-2 text-xs">
                      <div>
                        <div className="mb-1 flex justify-between">
                          <span className="text-zinc-400">GF</span>
                          <span className="font-bold text-white">{p.gf}</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                          <div
                            className="h-full rounded-full bg-sky-400"
                            style={{
                              width: `${Math.max(4, (p.gf / maxPeriodGoals) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>

                      <div>
                        <div className="mb-1 flex justify-between">
                          <span className="text-zinc-400">GA</span>
                          <span className="font-bold text-white">{p.ga}</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                          <div
                            className="h-full rounded-full bg-zinc-500"
                            style={{
                              width: `${Math.max(4, (p.ga / maxPeriodGoals) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* NHL EDGE Team Tracking */}
          {edge && (
            <section className="relative overflow-hidden rounded-2xl border border-sky-500/25 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent" />
              <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.12] via-transparent to-transparent px-5 py-4">
                <h2 className="text-base font-bold tracking-tight text-white">
                  NHL EDGE Team Tracking
                </h2>
              </div>

              <div className="space-y-6 p-5">
                {edge.metrics.length > 0 && (
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {edge.metrics.map((m) => (
                      <div
                        key={m.label}
                        className="rounded-xl border border-white/10 bg-black/45 p-4 tabular-nums"
                      >
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="text-xs text-zinc-400">
                            {m.label}
                          </span>
                          {m.rank !== null ? (
                            <span className="rounded-full border border-sky-400/40 bg-sky-500/15 px-2 py-0.5 text-[11px] font-semibold text-sky-300">
                              #{m.rank} NHL
                            </span>
                          ) : m.percentile !== null ? (
                            <span className="rounded-full border border-sky-400/40 bg-sky-500/15 px-2 py-0.5 text-[11px] font-semibold text-sky-300">
                              {m.percentile}th %ile
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1.5 text-xl font-bold text-sky-400">
                          {m.value}
                        </p>
                        {m.percentile !== null && (
                          <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-zinc-800">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-sky-500 to-sky-300 shadow-[0_0_10px_#38bdf8]"
                              style={{ width: `${Math.max(4, m.percentile)}%` }}
                            />
                          </div>
                        )}
                        {m.leagueAvg && (
                          <p className="mt-2 text-[11px] text-zinc-500">
                            League Avg: {m.leagueAvg}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {edge.zones && (
                  <div className="rounded-xl border border-white/10 bg-black/45 p-4">
                    <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="font-semibold uppercase tracking-wider text-zinc-300">
                        Team Zone Time Distribution
                      </span>
                      <div className="flex items-center gap-3">
                        {edge.zones.offensiveRank !== null && (
                          <span className="text-sky-300">
                            OZ Rank: #{edge.zones.offensiveRank} NHL
                          </span>
                        )}
                        {edge.zones.offensiveLeagueAvg !== null && (
                          <span className="text-zinc-500">
                            League Avg OZ: {edge.zones.offensiveLeagueAvg}%
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex h-3 overflow-hidden rounded-full bg-zinc-900">
                      <div
                        className="bg-sky-400"
                        style={{ width: `${edge.zones.offensive}%` }}
                      />
                      <div
                        className="bg-zinc-600"
                        style={{ width: `${edge.zones.neutral}%` }}
                      />
                      <div
                        className="bg-zinc-800"
                        style={{ width: `${edge.zones.defensive}%` }}
                      />
                    </div>
                    <div className="mt-2.5 flex flex-wrap justify-between gap-2 text-xs tabular-nums">
                      <span className="text-sky-300">
                        Offensive: {edge.zones.offensive}%
                      </span>
                      <span className="text-zinc-300">
                        Neutral: {edge.zones.neutral}%
                      </span>
                      <span className="text-zinc-400">
                        Defensive: {edge.zones.defensive}%
                      </span>
                    </div>
                  </div>
                )}

                {edge.shotLocations.length > 0 && (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    {edge.shotLocations.map((loc) => (
                      <div
                        key={loc.zone}
                        className="rounded-xl border border-white/10 bg-black/45 p-4 tabular-nums"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
                            {loc.zone}
                          </span>
                          {loc.shotsRank !== null && (
                            <span className="text-[11px] font-semibold text-sky-400">
                              #{loc.shotsRank} NHL
                            </span>
                          )}
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                          <div>
                            <p className="text-[10px] text-zinc-500">SOG</p>
                            <p className="font-bold text-white">{loc.shots}</p>
                          </div>
                          <div>
                            <p className="text-[10px] text-zinc-500">G</p>
                            <p className="font-bold text-white">{loc.goals}</p>
                          </div>
                          <div>
                            <p className="text-[10px] text-zinc-500">S%</p>
                            <p className="font-bold text-sky-400">
                              {loc.shootingPct}
                            </p>
                          </div>
                        </div>
                        {loc.leagueAvgPct && (
                          <p className="mt-2 text-center text-[10px] text-zinc-500">
                            League Avg S%: {loc.leagueAvgPct}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          <TeamMoneyPuckSection
            data={profile.moneyPuck}
            teamName={header.teamCommonName}
          />
        </div>
      )}

      {/* TAB 2: TEAM SKATERS, GOALIES & ROSTER BIOS */}
      {activeTab === "roster" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <p className="text-xs text-zinc-400">
              Click any player to open their full analytics page
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setRosterSubView("stats")}
                className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                  rosterSubView === "stats"
                    ? "border border-sky-400/50 bg-sky-500/15 text-sky-300"
                    : "border border-white/10 bg-black/40 text-zinc-400 hover:text-white"
                }`}
              >
                Season Stats
              </button>
              <button
                type="button"
                onClick={() => setRosterSubView("bios")}
                className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                  rosterSubView === "bios"
                    ? "border border-sky-400/50 bg-sky-500/15 text-sky-300"
                    : "border border-white/10 bg-black/40 text-zinc-400 hover:text-white"
                }`}
              >
                Active Roster Bios
              </button>
            </div>
          </div>

          {rosterSubView === "stats" ? (
            <>
              {/* Skaters Table */}
              <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
                <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.1] via-transparent to-transparent px-5 py-4">
                  <h2 className="text-base font-bold text-white">Skaters</h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-white/10 bg-black/45 text-xs uppercase tracking-wider text-zinc-400">
                        <th className="py-3.5 pl-5 pr-3 font-medium">Player</th>
                        {(
                          [
                            ["gp", "GP"],
                            ["goals", "G"],
                            ["assists", "A"],
                            ["points", "PTS"],
                            ["plusMinus", "+/-"],
                            ["ppGoals", "PPG"],
                            ["gwg", "GWG"],
                            ["shots", "SOG"],
                            ["shootingPct", "S%"],
                            ["pim", "PIM"],
                          ] as [SkaterSortKey, string][]
                        ).map(([key, label]) => (
                          <th
                            key={key}
                            onClick={() => toggleSkaterSort(key)}
                            className={`cursor-pointer select-none px-3 py-3.5 text-center font-medium transition hover:text-white ${
                              key === "points"
                                ? "font-semibold text-sky-400"
                                : ""
                            }`}
                          >
                            <span className="inline-flex items-center gap-1">
                              {label}
                              {skaterSort.key === key && (
                                <span className="text-[10px] text-sky-400">
                                  {skaterSort.dir === "asc" ? "▲" : "▼"}
                                </span>
                              )}
                            </span>
                          </th>
                        ))}
                        <th className="py-3.5 pl-3 pr-5 text-center font-medium">
                          TOI/G
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-sm tabular-nums">
                      {sortedSkaters.map((s) => (
                        <tr
                          key={s.playerId}
                          onClick={() => onSelectPlayer(s.playerId)}
                          className="cursor-pointer transition-colors hover:bg-sky-500/[0.08]"
                        >
                          <td className="py-3 pl-5 pr-3">
                            <div className="flex items-center gap-3">
                              <PlayerAvatar
                                src={s.headshotUrl}
                                name={s.fullName}
                                size="sm"
                              />
                              <div>
                                <p className="font-medium text-white">
                                  {s.fullName}
                                </p>
                                <p className="text-[11px] text-zinc-400">
                                  {s.sweaterNumber !== null
                                    ? `#${s.sweaterNumber} · `
                                    : ""}
                                  {s.position}
                                </p>
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.gp}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.goals}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.assists}
                          </td>
                          <td className="px-3 py-3 text-center font-bold text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.4)]">
                            {s.points}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.plusMinus > 0 ? `+${s.plusMinus}` : s.plusMinus}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.ppGoals}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.gwg}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.shots}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.shootingPct.toFixed(1)}%
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {s.pim}
                          </td>
                          <td className="py-3 pl-3 pr-5 text-center text-white">
                            {s.toiPerGame}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {/* Goalies Table */}
              <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
                <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.1] via-transparent to-transparent px-5 py-4">
                  <h2 className="text-base font-bold text-white">Goalies</h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-white/10 bg-black/45 text-xs uppercase tracking-wider text-zinc-400">
                        <th className="py-3.5 pl-5 pr-3 font-medium">Goalie</th>
                        <th className="px-3 py-3.5 text-center font-medium">
                          GP
                        </th>
                        <th className="px-3 py-3.5 text-center font-medium">
                          GS
                        </th>
                        <th className="px-3 py-3.5 text-center font-medium">
                          Record
                        </th>
                        <th className="px-3 py-3.5 text-center font-semibold text-sky-400">
                          SV%
                        </th>
                        <th className="px-3 py-3.5 text-center font-medium">
                          GAA
                        </th>
                        <th className="px-3 py-3.5 text-center font-medium">
                          SO
                        </th>
                        <th className="px-3 py-3.5 text-center font-medium">
                          SV
                        </th>
                        <th className="py-3.5 pl-3 pr-5 text-center font-medium">
                          SA
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-sm tabular-nums">
                      {goalies.map((g) => (
                        <tr
                          key={g.playerId}
                          onClick={() => onSelectPlayer(g.playerId)}
                          className="cursor-pointer transition-colors hover:bg-sky-500/[0.08]"
                        >
                          <td className="py-3 pl-5 pr-3">
                            <div className="flex items-center gap-3">
                              <PlayerAvatar
                                src={g.headshotUrl}
                                name={g.fullName}
                                size="sm"
                              />
                              <div>
                                <p className="font-medium text-white">
                                  {g.fullName}
                                </p>
                                {g.sweaterNumber !== null && (
                                  <p className="text-[11px] text-zinc-400">
                                    #{g.sweaterNumber} · G
                                  </p>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {g.gp}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {g.gs}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {g.record}
                          </td>
                          <td className="px-3 py-3 text-center font-bold text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.4)]">
                            {g.savePctDisplay}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {g.gaa.toFixed(2)}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {g.shutouts}
                          </td>
                          <td className="px-3 py-3 text-center text-white">
                            {g.saves}
                          </td>
                          <td className="py-3 pl-3 pr-5 text-center text-white">
                            {g.shotsAgainst}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : (
            <div className="space-y-6">
              {(
                [
                  ["Forwards", roster.forwards],
                  ["Defensemen", roster.defensemen],
                  ["Goalies", roster.goalies],
                ] as [string, RosterPerson[]][]
              ).map(([groupTitle, people]) => (
                <section
                  key={groupTitle}
                  className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17]"
                >
                  <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.1] via-transparent to-transparent px-5 py-3.5">
                    <h2 className="text-base font-bold text-white">
                      {groupTitle}
                    </h2>
                  </div>
                  <div className="grid grid-cols-1 gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
                    {people.map((p) => (
                      <button
                        key={p.playerId ?? p.fullName}
                        type="button"
                        onClick={() => {
                          if (p.playerId) onSelectPlayer(p.playerId);
                        }}
                        className="flex items-center gap-3.5 rounded-xl border border-white/10 bg-black/45 p-3.5 text-left transition hover:border-sky-400/40 hover:bg-sky-500/[0.07]"
                      >
                        <PlayerAvatar src={p.headshotUrl} name={p.fullName} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className="truncate font-semibold text-white">
                              {p.fullName}
                            </p>
                            {p.sweaterNumber !== null && (
                              <span className="text-xs font-bold text-sky-400 tabular-nums">
                                #{p.sweaterNumber}
                              </span>
                            )}
                          </div>
                          <p className="mt-0.5 text-xs text-zinc-400">
                            {p.position} · {p.height} · {p.weight} ·{" "}
                            {p.shootsCatches}
                          </p>
                          <p className="mt-0.5 truncate text-[11px] text-zinc-500">
                            {p.age !== null ? `Age ${p.age} · ` : ""}
                            {p.birthplace}
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: SCHEDULE & RECENT RESULTS */}
      {activeTab === "schedule" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Recent 10 Results */}
          <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
            <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.1] via-transparent to-transparent px-5 py-4">
              <h2 className="text-base font-bold text-white">Recent Results</h2>
            </div>
            <div className="divide-y divide-white/5">
              {recentGames.length === 0 && (
                <p className="p-8 text-center text-sm text-zinc-500">
                  No completed games found yet.
                </p>
              )}
              {recentGames.map((g) => (
                <div
                  key={g.gameId}
                  className="flex items-center justify-between gap-3 px-5 py-3.5 text-sm tabular-nums"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`inline-flex w-10 justify-center rounded-md py-1 text-xs font-bold ${
                        g.result === "W"
                          ? "border border-sky-400/40 bg-sky-500/15 text-sky-300"
                          : "border border-white/10 bg-white/5 text-zinc-300"
                      }`}
                    >
                      {g.result}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-zinc-400">
                          {g.isHome ? "vs" : "@"}
                        </span>
                        {g.opponentLogo && (
                          <img
                            src={g.opponentLogo}
                            alt={g.opponentAbbrev}
                            className="h-5 w-5 object-contain"
                          />
                        )}
                        <span className="font-semibold text-white">
                          {g.opponentAbbrev}
                        </span>
                      </div>
                      <p className="text-[11px] text-zinc-500">{g.date}</p>
                    </div>
                  </div>

                  <div className="text-right">
                    <p className="text-base font-bold text-white">
                      {g.teamScore} – {g.opponentScore}
                      {g.periodType && g.periodType !== "REG" && (
                        <span className="ml-1.5 text-xs font-medium text-sky-400">
                          {g.periodType}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Next 10 Upcoming Games */}
          <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
            <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.1] via-transparent to-transparent px-5 py-4">
              <h2 className="text-base font-bold text-white">
                Upcoming Schedule
              </h2>
            </div>
            <div className="divide-y divide-white/5">
              {upcomingGames.length === 0 && (
                <p className="p-8 text-center text-sm text-zinc-500">
                  No upcoming games scheduled.
                </p>
              )}
              {upcomingGames.map((g) => (
                <div
                  key={g.gameId}
                  className="flex items-center justify-between gap-3 px-5 py-3.5 text-sm tabular-nums"
                >
                  <div className="flex items-center gap-3">
                    <span className="inline-flex w-12 justify-center rounded-md border border-white/10 bg-black/50 py-1 text-[11px] font-semibold uppercase text-zinc-300">
                      {g.isHome ? "Home" : "Away"}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        {g.opponentLogo && (
                          <img
                            src={g.opponentLogo}
                            alt={g.opponentAbbrev}
                            className="h-5 w-5 object-contain"
                          />
                        )}
                        <span className="font-semibold text-white">
                          {g.isHome ? "vs" : "@"} {g.opponentAbbrev}
                        </span>
                      </div>
                      <p className="text-[11px] text-zinc-500">{g.venue}</p>
                    </div>
                  </div>

                  <div className="text-right">
                    <p className="font-semibold text-white">{g.date}</p>
                    <p className="text-xs text-sky-400">
                      {formatLocalTime(g.startTimeUTC)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {/* TAB 4: PROSPECTS */}
      {activeTab === "prospects" && (
        <div className="space-y-6">
          {totalProspects === 0 && (
            <div className="rounded-2xl border border-white/10 bg-[#0b0f17] p-10 text-center text-sm text-zinc-400">
              No prospect data available for {header.teamName}.
            </div>
          )}

          {(
            [
              ["Forward Prospects", prospects.forwards],
              ["Defense Prospects", prospects.defensemen],
              ["Goalie Prospects", prospects.goalies],
            ] as [string, RosterPerson[]][]
          )
            .filter(([, list]) => list.length > 0)
            .map(([groupTitle, list]) => (
              <section
                key={groupTitle}
                className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17]"
              >
                <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.1] via-transparent to-transparent px-5 py-3.5">
                  <h2 className="text-base font-bold text-white">
                    {groupTitle}
                  </h2>
                </div>
                <div className="grid grid-cols-1 gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
                  {list.map((p) => (
                    <button
                      key={p.playerId ?? p.fullName}
                      type="button"
                      onClick={() => {
                        if (p.playerId) onSelectPlayer(p.playerId);
                      }}
                      className="flex items-center gap-3.5 rounded-xl border border-white/10 bg-black/45 p-3.5 text-left transition hover:border-sky-400/40 hover:bg-sky-500/[0.07]"
                    >
                      <PlayerAvatar src={p.headshotUrl} name={p.fullName} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-semibold text-white">
                          {p.fullName}
                        </p>
                        <p className="mt-0.5 text-xs text-zinc-400">
                          {p.position} · {p.height} · {p.weight} ·{" "}
                          {p.shootsCatches}
                        </p>
                        <p className="mt-0.5 truncate text-[11px] text-zinc-500">
                          {p.age !== null ? `Age ${p.age} · ` : ""}
                          {p.birthplace}
                        </p>
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            ))}
        </div>
      )}
    </div>
  );
}
