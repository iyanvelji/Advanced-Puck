import { useState } from "react";
import type { MoneyPuckSituationKey } from "../types/players";
import type { TeamMoneyPuckData } from "../types/teams";
import {
  ExpectedVsActualChart,
  IceRadarChart,
  SituationalDominanceChart,
  TeamDangerComparisonChart,
} from "./AnalyticsCharts";

interface TeamMoneyPuckSectionProps {
  data: TeamMoneyPuckData | null | undefined;
  teamName: string;
}

const SITUATION_OPTIONS: { key: MoneyPuckSituationKey; label: string }[] = [
  { key: "5on5", label: "5v5" },
  { key: "all", label: "All Situations" },
  { key: "5on4", label: "5v4 Power Play" },
  { key: "4on5", label: "4v5 Penalty Kill" },
];

export default function TeamMoneyPuckSection({
  data,
  teamName,
}: TeamMoneyPuckSectionProps) {
  const [situation, setSituation] = useState<MoneyPuckSituationKey>(
    data?.defaultSituation ?? "5on5",
  );

  if (!data) return null;

  const active =
    data.situations[situation] ?? data.situations[data.defaultSituation];
  if (!active) return null;

  return (
    <div className="space-y-6 pt-2">
      {/* Section Header + Situation Switcher */}
      <div className="relative overflow-hidden rounded-2xl border border-sky-500/25 bg-[#0b0f17] px-5 py-4 shadow-[0_12px_36px_rgba(0,0,0,0.65)]">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent" />
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-lg font-bold text-white">
            MoneyPuck Team Analytics
          </h2>

          <div className="flex flex-wrap items-center gap-1.5">
            {SITUATION_OPTIONS.filter((opt) => data.situations[opt.key]).map(
              (opt) => {
                const isActive = situation === opt.key;
                return (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => setSituation(opt.key)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                      isActive
                        ? "border border-sky-400/50 bg-sky-500/15 text-sky-300 shadow-[0_0_14px_rgba(56,189,248,0.18)]"
                        : "border border-white/10 bg-black/45 text-zinc-400 hover:text-white"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              },
            )}
          </div>
        </div>
      </div>

      {/* MoneyPuck Ranked Stat Cards */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {active.statGroups.map((group) => (
          <section
            key={group.title}
            className="relative overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_12px_36px_rgba(0,0,0,0.65)]"
          >
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/50 to-transparent" />
            <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.1] via-transparent to-transparent px-5 py-3.5">
              <h3 className="text-base font-bold tracking-tight text-white">
                {group.title}
              </h3>
            </div>
            <div className="grid grid-cols-2 gap-3 p-5 sm:grid-cols-3">
              {group.items.map((item) => (
                <div
                  key={item.label}
                  className="rounded-xl border border-white/5 bg-black/45 px-3.5 py-3 tabular-nums"
                >
                  <div className="flex items-start justify-between gap-1">
                    <p className="text-[11px] text-zinc-400">{item.label}</p>
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

      {/* Bottom Interactive Charts Suite */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <IceRadarChart
          title={`${teamName} Identity Radar`}
          subtitle="Percentile rank across all 32 NHL teams"
          points={active.charts.radar}
        />

        <TeamDangerComparisonChart data={active.charts.dangerComparison} />

        <SituationalDominanceChart rows={data.situationalDominance} />

        <ExpectedVsActualChart
          title="Finishing & Goaltending Differential"
          subtitle="Actual goals vs. MoneyPuck expected goals"
          rows={active.charts.expectedVsActual}
        />
      </div>
    </div>
  );
}
