import { useEffect, useState } from "react";
import { fetchPlayerProfile } from "../api/players";
import type { PlayerProfileResponse } from "../types/players";
import PlayerAvatar from "./PlayerAvatar";
import PlayerMoneyPuckSection from "./PlayerMoneyPuckSection";

interface PlayerDetailViewProps {
  playerId: number;
  backLabel: string;
  onBack: () => void;
}

type DetailTab = "overview" | "gamelog" | "career";

export default function PlayerDetailView({
  playerId,
  backLabel,
  onBack,
}: PlayerDetailViewProps) {
  const [profile, setProfile] = useState<PlayerProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [nhlOnlyCareer, setNhlOnlyCareer] = useState(true);

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");
    setActiveTab("overview");

    fetchPlayerProfile(playerId)
      .then((res) => {
        if (!ignore) setProfile(res);
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load player profile",
          );
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [playerId]);

  if (loading) {
    return (
      <div className="space-y-6">
        <button
          type="button"
          onClick={onBack}
          className="rounded-xl border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-300 transition hover:bg-sky-500/20"
        >
          ← {backLabel}
        </button>
        <div className="rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-14 text-center text-sm text-zinc-400">
          Loading full player analytics, NHL EDGE tracking, and game logs...
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
          ← {backLabel}
        </button>
        <div className="rounded-2xl border border-red-500/30 bg-red-950/20 p-6 text-sm text-red-200">
          {error || "Player profile unavailable."}
        </div>
      </div>
    );
  }

  const {
    bio,
    headlineKpis,
    statGroups,
    edge,
    gameLog,
    careerTotals,
    seasonTotals,
    awards,
  } = profile;

  const displayedSeasons = nhlOnlyCareer
    ? seasonTotals.filter((s) => s.league === "NHL")
    : seasonTotals;

  const regCareer = careerTotals.regularSeason || {};
  const poCareer = careerTotals.playoffs || {};
  const hasPlayoffs = Number(poCareer.gamesPlayed ?? 0) > 0;

  return (
    <div className="space-y-6">
      {/* Top Back Bar */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="rounded-xl border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-300 transition hover:bg-sky-500/20"
        >
          ← {backLabel}
        </button>
        <span className="text-xs font-medium uppercase tracking-widest text-zinc-400">
          {profile.seasonLabel} Season Profile
        </span>
      </div>

      {/* Hero Profile Banner */}
      <section className="relative overflow-hidden rounded-2xl border border-sky-500/25 bg-[#0b0f17] shadow-[0_18px_55px_rgba(0,0,0,0.75)]">
        {bio.heroImageUrl && (
          <img
            src={bio.heroImageUrl}
            alt=""
            className="pointer-events-none absolute inset-0 h-full w-full object-cover object-top opacity-20"
          />
        )}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-[#05070a] via-[#0b0f17]/90 to-[#05070a]/75" />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/70 to-transparent" />

        <div className="relative p-6 sm:p-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            {/* Identity */}
            <div className="flex items-center gap-5">
              <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-2xl border border-sky-400/50 bg-[#05070a] shadow-[0_0_28px_rgba(56,189,248,0.28)] sm:h-28 sm:w-28">
                {bio.headshotUrl ? (
                  <img
                    src={bio.headshotUrl}
                    alt={bio.fullName}
                    className="h-full w-full object-cover object-top"
                  />
                ) : (
                  <PlayerAvatar src="" name={bio.fullName} isLeader />
                )}
              </div>

              <div>
                <div className="flex flex-wrap items-center gap-2.5">
                  {bio.sweaterNumber !== null && (
                    <span className="rounded-lg border border-sky-400/40 bg-sky-500/15 px-2.5 py-0.5 text-sm font-bold text-sky-300 tabular-nums">
                      #{bio.sweaterNumber}
                    </span>
                  )}
                  <span className="rounded-lg border border-white/10 bg-black/50 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-zinc-300">
                    {bio.position}
                  </span>
                  {bio.inHHOF && (
                    <span className="rounded-lg border border-sky-300/50 bg-sky-400/20 px-2.5 py-0.5 text-xs font-semibold text-sky-200">
                      Hall of Fame
                    </span>
                  )}
                </div>

                <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-white sm:text-4xl">
                  {bio.fullName}
                </h1>

                <div className="mt-2 flex items-center gap-2.5 text-sm text-zinc-300">
                  {bio.teamLogo && (
                    <img
                      src={bio.teamLogo}
                      alt={bio.teamAbbrev}
                      className="h-6 w-6 object-contain"
                    />
                  )}
                  <span className="font-medium text-white">{bio.teamName}</span>
                </div>
              </div>
            </div>

            {/* Bio Details Grid */}
            <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 rounded-xl border border-white/10 bg-black/50 px-5 py-4 text-xs backdrop-blur-sm sm:grid-cols-3">
              <div>
                <p className="uppercase tracking-wider text-zinc-500">
                  Height / Wt
                </p>
                <p className="mt-0.5 font-semibold text-white">
                  {bio.height} · {bio.weight}
                </p>
              </div>
              <div>
                <p className="uppercase tracking-wider text-zinc-500">
                  {profile.isGoalie ? "Catches" : "Shoots"}
                </p>
                <p className="mt-0.5 font-semibold text-white">
                  {bio.shootsCatches}
                </p>
              </div>
              <div>
                <p className="uppercase tracking-wider text-zinc-500">
                  Age / Born
                </p>
                <p className="mt-0.5 font-semibold text-white">
                  {bio.age !== null
                    ? `${bio.age} (${bio.birthDate})`
                    : bio.birthDate}
                </p>
              </div>
              <div className="col-span-2 sm:col-span-2">
                <p className="uppercase tracking-wider text-zinc-500">
                  Birthplace
                </p>
                <p className="mt-0.5 font-semibold text-white">
                  {bio.birthplace}
                </p>
              </div>
              <div className="col-span-2 sm:col-span-3">
                <p className="uppercase tracking-wider text-zinc-500">
                  NHL Draft
                </p>
                <p className="mt-0.5 font-semibold text-white">{bio.draft}</p>
              </div>
            </div>
          </div>

          {/* 6 Headline Season KPI Cards */}
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
                    {kpi.rank}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Sub-Navigation Tabs */}
        <div className="relative grid grid-cols-3 border-t border-white/10 bg-black/45">
          {(
            [
              ["overview", "Season & Advanced"],
              ["gamelog", `Game Log (${gameLog.length})`],
              ["career", "Career & Awards"],
            ] as [DetailTab, string][]
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

      {/* TAB 1: SEASON, ADVANCED & NHL EDGE */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Categorized Stat Panels */}
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

          {/* NHL EDGE Player Tracking Panel */}
          {edge && (
            <section className="relative overflow-hidden rounded-2xl border border-sky-500/25 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent" />
              <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.12] via-transparent to-transparent px-5 py-4">
                <h2 className="text-base font-bold tracking-tight text-white">
                  NHL EDGE Tracking &amp; Percentiles
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
                          {m.percentile !== null && (
                            <span className="rounded-full border border-sky-400/40 bg-sky-500/15 px-2 py-0.5 text-[11px] font-semibold text-sky-300">
                              {m.percentile}th %ile
                            </span>
                          )}
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
                    <div className="mb-2.5 flex items-center justify-between text-xs">
                      <span className="font-semibold uppercase tracking-wider text-zinc-300">
                        Zone Time Distribution
                      </span>
                      {edge.zones.offensivePercentile !== null && (
                        <span className="text-sky-300">
                          OZ Time: {edge.zones.offensivePercentile}th %ile
                        </span>
                      )}
                    </div>
                    <div className="flex h-3 overflow-hidden rounded-full bg-zinc-900">
                      <div
                        className="bg-sky-400"
                        style={{ width: `${edge.zones.offensive}%` }}
                        title={`Offensive Zone: ${edge.zones.offensive}%`}
                      />
                      <div
                        className="bg-zinc-600"
                        style={{ width: `${edge.zones.neutral}%` }}
                        title={`Neutral Zone: ${edge.zones.neutral}%`}
                      />
                      <div
                        className="bg-zinc-800"
                        style={{ width: `${edge.zones.defensive}%` }}
                        title={`Defensive Zone: ${edge.zones.defensive}%`}
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
                          {loc.percentile !== null && (
                            <span className="text-[11px] font-semibold text-sky-400">
                              {loc.percentile}th %ile
                            </span>
                          )}
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                          <div>
                            <p className="text-[10px] text-zinc-500">
                              {profile.isGoalie ? "SA" : "SOG"}
                            </p>
                            <p className="font-bold text-white">{loc.shots}</p>
                          </div>
                          <div>
                            <p className="text-[10px] text-zinc-500">
                              {profile.isGoalie ? "GA" : "G"}
                            </p>
                            <p className="font-bold text-white">{loc.goals}</p>
                          </div>
                          <div>
                            <p className="text-[10px] text-zinc-500">
                              {profile.isGoalie ? "SV%" : "S%"}
                            </p>
                            <p className="font-bold text-sky-400">
                              {loc.shootingPct}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          <PlayerMoneyPuckSection
            data={profile.moneyPuck}
            isGoalie={profile.isGoalie}
          />
        </div>
      )}

      {/* TAB 2: CURRENT SEASON GAME LOG */}
      {activeTab === "gamelog" && (
        <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-white/10 bg-black/45 text-xs uppercase tracking-wider text-zinc-400">
                  <th className="py-3.5 pl-5 pr-3 font-medium">Date</th>
                  <th className="px-3 py-3.5 font-medium">Matchup</th>
                  {profile.isGoalie ? (
                    <>
                      <th className="px-3 py-3.5 text-center font-medium">
                        Dec
                      </th>
                      <th className="px-3 py-3.5 text-center font-medium">
                        SA
                      </th>
                      <th className="px-3 py-3.5 text-center font-medium">
                        GA
                      </th>
                      <th className="px-3 py-3.5 text-center font-semibold text-sky-400">
                        SV%
                      </th>
                      <th className="px-3 py-3.5 text-center font-medium">
                        SO
                      </th>
                      <th className="py-3.5 pl-3 pr-5 text-center font-medium">
                        TOI
                      </th>
                    </>
                  ) : (
                    <>
                      <th className="px-3 py-3.5 text-center font-medium">G</th>
                      <th className="px-3 py-3.5 text-center font-medium">A</th>
                      <th className="px-3 py-3.5 text-center font-semibold text-sky-400">
                        PTS
                      </th>
                      <th className="px-3 py-3.5 text-center font-medium">
                        +/-
                      </th>
                      <th className="px-3 py-3.5 text-center font-medium">
                        SOG
                      </th>
                      <th className="px-3 py-3.5 text-center font-medium">
                        PPG
                      </th>
                      <th className="px-3 py-3.5 text-center font-medium">
                        PPP
                      </th>
                      <th className="px-3 py-3.5 text-center font-medium">
                        PIM
                      </th>
                      <th className="py-3.5 pl-3 pr-5 text-center font-medium">
                        TOI
                      </th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-sm tabular-nums">
                {gameLog.length === 0 && (
                  <tr>
                    <td
                      colSpan={11}
                      className="px-5 py-10 text-center text-zinc-500"
                    >
                      No game logs available for the current season.
                    </td>
                  </tr>
                )}
                {gameLog.map((g, idx) => (
                  <tr
                    key={`${g.gameId ?? g.date}-${idx}`}
                    className="transition-colors hover:bg-sky-500/[0.06]"
                  >
                    <td className="py-3 pl-5 pr-3 text-zinc-300">{g.date}</td>
                    <td className="px-3 py-3 font-medium text-white">
                      {g.homeRoad === "H" ? "vs" : "@"} {g.opponent}
                    </td>
                    {profile.isGoalie ? (
                      <>
                        <td className="px-3 py-3 text-center text-white">
                          {g.decision || "—"}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.shotsAgainst ?? "—"}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.goalsAgainst ?? "—"}
                        </td>
                        <td className="px-3 py-3 text-center font-bold text-sky-400">
                          {g.savePct}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.shutouts}
                        </td>
                        <td className="py-3 pl-3 pr-5 text-center text-white">
                          {g.toi}
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-3 py-3 text-center text-white">
                          {g.goals}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.assists}
                        </td>
                        <td className="px-3 py-3 text-center font-bold text-sky-400">
                          {g.points}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.plusMinus > 0 ? `+${g.plusMinus}` : g.plusMinus}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.shots}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.ppGoals}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.ppPoints}
                        </td>
                        <td className="px-3 py-3 text-center text-white">
                          {g.pim}
                        </td>
                        <td className="py-3 pl-3 pr-5 text-center text-white">
                          {g.toi}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* TAB 3: CAREER TOTALS, SEASON-BY-SEASON & AWARDS */}
      {activeTab === "career" && (
        <div className="space-y-6">
          {/* Career Summary Cards */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {[
              {
                title: "NHL Career · Regular Season",
                stats: regCareer,
                show: true,
              },
              {
                title: "NHL Career · Playoffs",
                stats: poCareer,
                show: hasPlayoffs,
              },
            ]
              .filter((c) => c.show)
              .map((card) => (
                <section
                  key={card.title}
                  className="rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5"
                >
                  <h2 className="mb-4 text-base font-bold text-white">
                    {card.title}
                  </h2>
                  <div className="grid grid-cols-3 gap-3 text-center tabular-nums sm:grid-cols-5">
                    {profile.isGoalie ? (
                      <>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">GP</p>
                          <p className="mt-1 font-bold text-white">
                            {card.stats.gamesPlayed ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">W</p>
                          <p className="mt-1 font-bold text-white">
                            {card.stats.wins ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">SV%</p>
                          <p className="mt-1 font-bold text-sky-400">
                            {card.stats.savePctg !== undefined &&
                            card.stats.savePctg !== null
                              ? Number(card.stats.savePctg)
                                  .toFixed(3)
                                  .replace(/^0/, "")
                              : "—"}
                          </p>
                        </div>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">GAA</p>
                          <p className="mt-1 font-bold text-white">
                            {card.stats.goalsAgainstAvg !== undefined &&
                            card.stats.goalsAgainstAvg !== null
                              ? Number(card.stats.goalsAgainstAvg).toFixed(2)
                              : "—"}
                          </p>
                        </div>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">SO</p>
                          <p className="mt-1 font-bold text-white">
                            {card.stats.shutouts ?? 0}
                          </p>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">GP</p>
                          <p className="mt-1 font-bold text-white">
                            {card.stats.gamesPlayed ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">G</p>
                          <p className="mt-1 font-bold text-white">
                            {card.stats.goals ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">A</p>
                          <p className="mt-1 font-bold text-white">
                            {card.stats.assists ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">PTS</p>
                          <p className="mt-1 font-bold text-sky-400">
                            {card.stats.points ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl bg-black/50 p-3">
                          <p className="text-[11px] text-zinc-400">+/-</p>
                          <p className="mt-1 font-bold text-white">
                            {Number(card.stats.plusMinus ?? 0) > 0
                              ? `+${card.stats.plusMinus}`
                              : (card.stats.plusMinus ?? 0)}
                          </p>
                        </div>
                      </>
                    )}
                  </div>
                </section>
              ))}
          </div>

          {/* Trophies & Awards */}
          {awards.length > 0 && (
            <section className="rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5">
              <h2 className="mb-4 text-base font-bold text-white">
                NHL Awards &amp; Honors
              </h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {awards.map((aw) => (
                  <div
                    key={aw.trophy}
                    className="rounded-xl border border-sky-400/25 bg-black/50 p-4"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-semibold text-white">{aw.trophy}</p>
                      <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-xs font-bold text-sky-300">
                        ×{aw.count}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs text-zinc-400">
                      {aw.seasons.join(", ")}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Season-by-Season Career Table */}
          <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
              <h2 className="text-base font-bold text-white">
                Season-by-Season History
              </h2>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setNhlOnlyCareer(true)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    nhlOnlyCareer
                      ? "border border-sky-400/50 bg-sky-500/15 text-sky-300"
                      : "border border-white/10 bg-black/40 text-zinc-400 hover:text-white"
                  }`}
                >
                  NHL Only
                </button>
                <button
                  type="button"
                  onClick={() => setNhlOnlyCareer(false)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    !nhlOnlyCareer
                      ? "border border-sky-400/50 bg-sky-500/15 text-sky-300"
                      : "border border-white/10 bg-black/40 text-zinc-400 hover:text-white"
                  }`}
                >
                  All Leagues
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-white/10 bg-black/45 text-xs uppercase tracking-wider text-zinc-400">
                    <th className="py-3 pl-5 pr-3 font-medium">Season</th>
                    <th className="px-3 py-3 font-medium">Team</th>
                    <th className="px-3 py-3 font-medium">League</th>
                    <th className="px-3 py-3 font-medium">Type</th>
                    <th className="px-3 py-3 text-center font-medium">GP</th>
                    {profile.isGoalie ? (
                      <>
                        <th className="px-3 py-3 text-center font-medium">W</th>
                        <th className="px-3 py-3 text-center font-medium">L</th>
                        <th className="px-3 py-3 text-center font-medium">
                          OTL
                        </th>
                        <th className="px-3 py-3 text-center font-semibold text-sky-400">
                          SV%
                        </th>
                        <th className="px-3 py-3 text-center font-medium">
                          GAA
                        </th>
                        <th className="py-3 pl-3 pr-5 text-center font-medium">
                          SO
                        </th>
                      </>
                    ) : (
                      <>
                        <th className="px-3 py-3 text-center font-medium">G</th>
                        <th className="px-3 py-3 text-center font-medium">A</th>
                        <th className="px-3 py-3 text-center font-semibold text-sky-400">
                          PTS
                        </th>
                        <th className="px-3 py-3 text-center font-medium">
                          +/-
                        </th>
                        <th className="px-3 py-3 text-center font-medium">
                          PIM
                        </th>
                        <th className="px-3 py-3 text-center font-medium">
                          PPG
                        </th>
                        <th className="py-3 pl-3 pr-5 text-center font-medium">
                          TOI/G
                        </th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-sm tabular-nums">
                  {displayedSeasons.map((row, idx) => (
                    <tr
                      key={`${row.season}-${row.team}-${row.gameType}-${idx}`}
                      className="transition-colors hover:bg-sky-500/[0.06]"
                    >
                      <td className="py-2.5 pl-5 pr-3 font-medium text-white">
                        {row.season}
                      </td>
                      <td className="px-3 py-2.5 text-zinc-200">{row.team}</td>
                      <td className="px-3 py-2.5 text-zinc-400">
                        {row.league}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-zinc-400">
                        {row.gameType}
                      </td>
                      <td className="px-3 py-2.5 text-center text-white">
                        {row.gp}
                      </td>
                      {profile.isGoalie ? (
                        <>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.wins ?? "—"}
                          </td>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.losses ?? "—"}
                          </td>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.otLosses ?? "—"}
                          </td>
                          <td className="px-3 py-2.5 text-center font-bold text-sky-400">
                            {row.savePct}
                          </td>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.gaa !== null ? row.gaa.toFixed(2) : "—"}
                          </td>
                          <td className="py-2.5 pl-3 pr-5 text-center text-white">
                            {row.shutouts ?? "—"}
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.goals}
                          </td>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.assists}
                          </td>
                          <td className="px-3 py-2.5 text-center font-bold text-sky-400">
                            {row.points}
                          </td>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.plusMinus !== null
                              ? row.plusMinus > 0
                                ? `+${row.plusMinus}`
                                : row.plusMinus
                              : "—"}
                          </td>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.pim}
                          </td>
                          <td className="px-3 py-2.5 text-center text-white">
                            {row.ppGoals ?? "—"}
                          </td>
                          <td className="py-2.5 pl-3 pr-5 text-center text-white">
                            {row.avgToi}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
