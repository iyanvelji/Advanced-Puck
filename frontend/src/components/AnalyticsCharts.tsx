import { useState } from "react";
import type {
  DangerBarPoint,
  ExpectedVsActualRow,
  OnOffImpactRow,
  RadarAxisPoint,
  ShiftStartSlice,
} from "../types/players";
import type {
  SituationalDominancePoint,
  TeamDangerComparisonPoint,
} from "../types/teams";

/* 1. 6-Axis Glowing Ice-Blue Radar / Percentile Chart */
export function IceRadarChart({
  title,
  subtitle,
  points,
}: {
  title: string;
  subtitle: string;
  points: RadarAxisPoint[];
}) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  if (!points.length) return null;

  const size = 300;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = 96;
  const rings = [25, 50, 75, 100];

  const getCoord = (index: number, pct: number) => {
    const angle = (Math.PI * 2 * index) / points.length - Math.PI / 2;
    const r = (Math.max(4, Math.min(100, pct)) / 100) * maxR;
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    };
  };

  const polygonPoints = points
    .map((p, i) => {
      const { x, y } = getCoord(i, p.percentile);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const active = hoveredIdx !== null ? points[hoveredIdx] : null;

  return (
    <div className="flex flex-col rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5 shadow-[0_12px_36px_rgba(0,0,0,0.65)]">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-white">{title}</h3>
          <p className="text-xs text-zinc-400">{subtitle}</p>
        </div>
        {active ? (
          <div className="rounded-lg border border-sky-400/40 bg-sky-500/15 px-2.5 py-1 text-right text-xs tabular-nums">
            <p className="font-bold text-sky-300">{active.percentile}th %ile</p>
            <p className="text-[11px] text-white">{active.display}</p>
          </div>
        ) : (
          <span className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1 text-[11px] text-zinc-400">
            Hover points
          </span>
        )}
      </div>

      <div className="my-auto flex items-center justify-center py-2">
        <svg
          viewBox={`0 0 ${size} ${size}`}
          className="h-64 w-full max-w-[300px]"
        >
          <defs>
            <radialGradient id="iceRadarFill" cx="50%" cy="50%" r="55%">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.45" />
              <stop offset="100%" stopColor="#0284c7" stopOpacity="0.12" />
            </radialGradient>
          </defs>

          {/* Concentric Polygon Grid */}
          {rings.map((ring) => {
            const ringPts = points
              .map((_, i) => {
                const { x, y } = getCoord(i, ring);
                return `${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .join(" ");
            return (
              <polygon
                key={ring}
                points={ringPts}
                fill="none"
                stroke={
                  ring === 50
                    ? "rgba(56,189,248,0.28)"
                    : "rgba(255,255,255,0.09)"
                }
                strokeDasharray={ring === 50 ? "3 3" : undefined}
                strokeWidth="1"
              />
            );
          })}

          {/* Axis Spokes & Labels */}
          {points.map((p, i) => {
            const end = getCoord(i, 100);
            const labelPos = getCoord(i, 126);
            return (
              <g key={p.axis}>
                <line
                  x1={cx}
                  y1={cy}
                  x2={end.x}
                  y2={end.y}
                  stroke="rgba(255,255,255,0.09)"
                  strokeWidth="1"
                />
                <text
                  x={labelPos.x}
                  y={labelPos.y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="fill-zinc-300 text-[10px] font-semibold"
                >
                  {p.axis}
                </text>
              </g>
            );
          })}

          {/* Data Polygon */}
          <polygon
            points={polygonPoints}
            fill="url(#iceRadarFill)"
            stroke="#38bdf8"
            strokeWidth="2.2"
            style={{ filter: "drop-shadow(0 0 8px rgba(56,189,248,0.45))" }}
          />

          {/* Interactive Vertices */}
          {points.map((p, i) => {
            const { x, y } = getCoord(i, p.percentile);
            const isHovered = hoveredIdx === i;
            return (
              <g
                key={p.axis}
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
                className="cursor-pointer"
              >
                <circle cx={x} cy={y} r={12} fill="transparent" />
                <circle
                  cx={x}
                  cy={y}
                  r={isHovered ? 6 : 4}
                  fill={isHovered ? "#e0f2fe" : "#38bdf8"}
                  stroke="#05070a"
                  strokeWidth="1.5"
                />
              </g>
            );
          })}
        </svg>
      </div>

      {/* Compact Percentile Legend */}
      <div className="mt-2 grid grid-cols-3 gap-2 text-center text-[11px] tabular-nums">
        {points.map((p, i) => (
          <div
            key={p.axis}
            onMouseEnter={() => setHoveredIdx(i)}
            onMouseLeave={() => setHoveredIdx(null)}
            className={`cursor-pointer rounded-lg border px-2 py-1.5 transition ${
              hoveredIdx === i
                ? "border-sky-400/50 bg-sky-500/15"
                : "border-white/5 bg-black/45"
            }`}
          >
            <p className="truncate text-[10px] text-zinc-400">{p.axis}</p>
            <p className="font-bold text-sky-400">{p.percentile}%</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* 2. Player Shot Danger Grouped Bar Chart (xG vs Actual Goals) */
export function PlayerDangerChart({
  data,
  isGoalie,
}: {
  data: DangerBarPoint[];
  isGoalie: boolean;
}) {
  if (!data.length) return null;
  const maxVal = Math.max(1, ...data.flatMap((d) => [d.expected, d.actual]));

  return (
    <div className="flex flex-col rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5 shadow-[0_12px_36px_rgba(0,0,0,0.65)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-white">
            {isGoalie
              ? "Danger Zone xGA vs. Goals Allowed"
              : "Shot Danger xG vs. Actual Goals"}
          </h3>
          <p className="text-xs text-zinc-400">
            Finishing &amp; shot quality by danger tier
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-zinc-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-sky-400" />
            {isGoalie ? "xGA" : "xG"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-white" />
            {isGoalie ? "GA" : "Goals"}
          </span>
        </div>
      </div>

      <div className="my-auto grid grid-cols-3 gap-4 pt-4">
        {data.map((d) => {
          const expH = Math.max(4, (d.expected / maxVal) * 140);
          const actH = Math.max(4, (d.actual / maxVal) * 140);
          const delta = isGoalie
            ? d.expected - d.actual
            : d.actual - d.expected;

          return (
            <div
              key={d.zone}
              className="flex flex-col items-center rounded-xl border border-white/5 bg-black/45 p-3 tabular-nums"
            >
              <div className="flex h-40 items-end gap-2.5">
                <div className="flex flex-col items-center">
                  <span className="mb-1 text-[10px] font-semibold text-sky-300">
                    {d.expected.toFixed(1)}
                  </span>
                  <div
                    className="w-6 rounded-t-md bg-gradient-to-t from-sky-600 to-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.35)]"
                    style={{ height: `${expH}px` }}
                  />
                </div>
                <div className="flex flex-col items-center">
                  <span className="mb-1 text-[10px] font-semibold text-white">
                    {d.actual}
                  </span>
                  <div
                    className="w-6 rounded-t-md bg-gradient-to-t from-zinc-400 to-white"
                    style={{ height: `${actH}px` }}
                  />
                </div>
              </div>

              <p className="mt-3 text-xs font-semibold text-white">{d.zone}</p>
              <p className="text-[11px] text-zinc-400">{d.shots} shots</p>
              <p
                className={`mt-1 text-[11px] font-bold ${
                  delta >= 0 ? "text-sky-400" : "text-zinc-400"
                }`}
              >
                {delta >= 0 ? `+${delta.toFixed(2)}` : delta.toFixed(2)}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* 3. Skater On-Ice vs Off-Ice Impact Bars + Shift Deployment */
export function OnOffImpactChart({
  impact,
  shiftStarts,
}: {
  impact: OnOffImpactRow[];
  shiftStarts: ShiftStartSlice[];
}) {
  const totalStarts = shiftStarts.reduce((acc, s) => acc + s.count, 0);
  const startColors = [
    "bg-sky-400",
    "bg-sky-300/60",
    "bg-zinc-600",
    "bg-zinc-800",
  ];

  return (
    <div className="flex flex-col justify-between gap-5 rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5 shadow-[0_12px_36px_rgba(0,0,0,0.65)]">
      <div>
        <h3 className="text-base font-bold text-white">
          On-Ice vs. Off-Ice Team Impact
        </h3>
        <p className="text-xs text-zinc-400">
          Team share with player on the ice compared to on the bench
        </p>

        <div className="mt-4 space-y-4 tabular-nums">
          {impact.map((row) => (
            <div key={row.label} className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-white">{row.label}</span>
                <span
                  className={`rounded-md px-2 py-0.5 font-bold ${
                    row.rel >= 0
                      ? "bg-sky-500/15 text-sky-300"
                      : "bg-white/5 text-zinc-400"
                  }`}
                >
                  {row.rel >= 0
                    ? `+${row.rel.toFixed(1)}%`
                    : `${row.rel.toFixed(1)}%`}{" "}
                  Rel
                </span>
              </div>

              <div className="space-y-1">
                <div className="relative flex items-center gap-2 text-[11px]">
                  <span className="w-12 text-sky-300">On-Ice</span>
                  <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-zinc-900">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-sky-600 to-sky-400"
                      style={{ width: `${Math.min(100, row.onIce)}%` }}
                    />
                    <div className="absolute inset-y-0 left-1/2 w-px bg-white/40" />
                  </div>
                  <span className="w-11 text-right font-bold text-sky-400">
                    {row.onIce.toFixed(1)}%
                  </span>
                </div>

                <div className="relative flex items-center gap-2 text-[11px]">
                  <span className="w-12 text-zinc-400">Off-Ice</span>
                  <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-zinc-900">
                    <div
                      className="h-full rounded-full bg-zinc-500"
                      style={{ width: `${Math.min(100, row.offIce)}%` }}
                    />
                    <div className="absolute inset-y-0 left-1/2 w-px bg-white/40" />
                  </div>
                  <span className="w-11 text-right text-zinc-300">
                    {row.offIce.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {totalStarts > 0 && (
        <div className="border-t border-white/10 pt-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">
            Shift Start Deployment ({totalStarts} shifts)
          </p>
          <div className="flex h-3 overflow-hidden rounded-full bg-zinc-900">
            {shiftStarts.map((s, idx) => (
              <div
                key={s.label}
                className={startColors[idx % startColors.length]}
                style={{ width: `${(s.count / totalStarts) * 100}%` }}
                title={`${s.label}: ${s.count}`}
              />
            ))}
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-2 text-xs tabular-nums sm:grid-cols-4">
            {shiftStarts.map((s, idx) => (
              <div key={s.label} className="flex items-center gap-1.5">
                <span
                  className={`h-2 w-2 rounded-full ${
                    startColors[idx % startColors.length]
                  }`}
                />
                <span className="text-zinc-400">{s.label}:</span>
                <span className="font-semibold text-white">
                  {((s.count / totalStarts) * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* 4. Expected vs Actual Goals Differential Chart (Shared) */
export function ExpectedVsActualChart({
  title,
  subtitle,
  rows,
}: {
  title: string;
  subtitle: string;
  rows: ExpectedVsActualRow[];
}) {
  if (!rows.length) return null;
  const maxVal = Math.max(1, ...rows.flatMap((r) => [r.expected, r.actual]));

  return (
    <div className="rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5 shadow-[0_12px_36px_rgba(0,0,0,0.65)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-white">{title}</h3>
          <p className="text-xs text-zinc-400">{subtitle}</p>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-zinc-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-sky-400" />
            Expected (xG)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-white" />
            Actual
          </span>
        </div>
      </div>

      <div className="space-y-4 tabular-nums">
        {rows.map((r) => (
          <div
            key={r.label}
            className="rounded-xl border border-white/5 bg-black/45 p-3.5"
          >
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-semibold text-white">{r.label}</span>
              <span
                className={`rounded-md px-2 py-0.5 font-bold ${
                  r.delta >= 0
                    ? "bg-sky-500/15 text-sky-300"
                    : "bg-white/5 text-zinc-400"
                }`}
              >
                {r.deltaLabel}:{" "}
                {r.delta >= 0 ? `+${r.delta.toFixed(2)}` : r.delta.toFixed(2)}
              </span>
            </div>

            <div className="space-y-1.5 text-[11px]">
              <div className="flex items-center gap-2">
                <span className="w-16 text-sky-300">Expected</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-zinc-900">
                  <div
                    className="h-full rounded-full bg-sky-400"
                    style={{
                      width: `${Math.max(3, (r.expected / maxVal) * 100)}%`,
                    }}
                  />
                </div>
                <span className="w-12 text-right font-semibold text-sky-300">
                  {r.expected.toFixed(1)}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="w-16 text-zinc-300">Actual</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-zinc-900">
                  <div
                    className="h-full rounded-full bg-white"
                    style={{
                      width: `${Math.max(3, (r.actual / maxVal) * 100)}%`,
                    }}
                  />
                </div>
                <span className="w-12 text-right font-semibold text-white">
                  {r.actual.toFixed(0)}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* 5. Team Danger Zone xGF vs xGA Comparison */
export function TeamDangerComparisonChart({
  data,
}: {
  data: TeamDangerComparisonPoint[];
}) {
  if (!data.length) return null;
  const maxVal = Math.max(1, ...data.flatMap((d) => [d.xGF, d.xGA]));

  return (
    <div className="flex flex-col rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5 shadow-[0_12px_36px_rgba(0,0,0,0.65)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-white">
            Shot Danger xG For vs. Against
          </h3>
          <p className="text-xs text-zinc-400">
            Expected goals created and conceded by danger tier
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-zinc-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-sky-400" />
            xG For
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-zinc-500" />
            xG Against
          </span>
        </div>
      </div>

      <div className="my-auto grid grid-cols-3 gap-4 pt-3">
        {data.map((d) => {
          const forH = Math.max(4, (d.xGF / maxVal) * 140);
          const agH = Math.max(4, (d.xGA / maxVal) * 140);
          const diff = d.xGF - d.xGA;

          return (
            <div
              key={d.zone}
              className="flex flex-col items-center rounded-xl border border-white/5 bg-black/45 p-3 tabular-nums"
            >
              <div className="flex h-40 items-end gap-2.5">
                <div className="flex flex-col items-center">
                  <span className="mb-1 text-[10px] font-semibold text-sky-300">
                    {d.xGF.toFixed(1)}
                  </span>
                  <div
                    className="w-6 rounded-t-md bg-gradient-to-t from-sky-600 to-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.35)]"
                    style={{ height: `${forH}px` }}
                  />
                </div>
                <div className="flex flex-col items-center">
                  <span className="mb-1 text-[10px] font-semibold text-zinc-300">
                    {d.xGA.toFixed(1)}
                  </span>
                  <div
                    className="w-6 rounded-t-md bg-zinc-600"
                    style={{ height: `${agH}px` }}
                  />
                </div>
              </div>

              <p className="mt-3 text-xs font-semibold text-white">{d.zone}</p>
              <p className="text-[10px] text-zinc-400">
                G: {d.goalsFor} – {d.goalsAgainst}
              </p>
              <p
                className={`mt-1 text-[11px] font-bold ${
                  diff >= 0 ? "text-sky-400" : "text-zinc-400"
                }`}
              >
                {diff >= 0 ? `+${diff.toFixed(1)}` : diff.toFixed(1)} xGD
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* 6. Team Situational Dominance Chart (5v5, All, PP, PK) */
export function SituationalDominanceChart({
  rows,
}: {
  rows: SituationalDominancePoint[];
}) {
  if (!rows.length) return null;

  return (
    <div className="rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5 shadow-[0_12px_36px_rgba(0,0,0,0.65)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-white">
            Situational Possession &amp; xG Share
          </h3>
          <p className="text-xs text-zinc-400">
            50% dashed benchmark across every game state
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-zinc-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-sky-400" />
            xG%
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-sky-200/70" />
            Corsi%
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-zinc-400" />
            Fenwick%
          </span>
        </div>
      </div>

      <div className="space-y-4 tabular-nums">
        {rows.map((r) => (
          <div
            key={r.situation}
            className="rounded-xl border border-white/5 bg-black/45 p-3.5"
          >
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-bold text-white">{r.situation}</span>
              <span className="text-sky-400 font-semibold">
                {r.xgPct.toFixed(1)}% xG · {r.corsiPct.toFixed(1)}% CF
              </span>
            </div>

            <div className="space-y-1.5">
              {[
                { label: "xG%", val: r.xgPct, bar: "bg-sky-400" },
                { label: "CF%", val: r.corsiPct, bar: "bg-sky-200/70" },
                { label: "FF%", val: r.fenwickPct, bar: "bg-zinc-400" },
              ].map((m) => (
                <div
                  key={m.label}
                  className="flex items-center gap-2 text-[11px]"
                >
                  <span className="w-8 text-zinc-400">{m.label}</span>
                  <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-zinc-900">
                    <div
                      className={`h-full rounded-full ${m.bar}`}
                      style={{ width: `${Math.min(100, m.val)}%` }}
                    />
                    <div className="absolute inset-y-0 left-1/2 w-px bg-white/40" />
                  </div>
                  <span className="w-11 text-right font-semibold text-white">
                    {m.val.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
