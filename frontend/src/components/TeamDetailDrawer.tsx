import type { TeamStanding } from "../types/standings";

interface TeamDetailDrawerProps {
  team: TeamStanding;
  onSelectTeam: (teamAbbrev: string) => void;
}

export default function TeamDetailDrawer({
  team,
  onSelectTeam,
}: TeamDetailDrawerProps) {
  return (
    <tr className="border-b border-sky-500/15 bg-[#070b12]">
      <td colSpan={11} className="px-5 py-5">
        <div className="grid gap-4 md:grid-cols-3">
          {/* Per-Game Metrics */}
          <div className="rounded-xl border border-white/10 bg-[#0b0f17] p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-sky-400">
              Per-Game Efficiency
            </p>
            <div className="grid grid-cols-2 gap-3 text-sm tabular-nums">
              <div>
                <p className="text-xs text-zinc-400">Point %</p>
                <p className="font-semibold text-white">
                  {(team.pointPctg * 100).toFixed(1)}%
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-400">Diff / GP</p>
                <p className="font-semibold text-white">
                  {team.diffPerGame > 0
                    ? `+${team.diffPerGame}`
                    : team.diffPerGame}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-400">GF / GP</p>
                <p className="font-semibold text-white">{team.gfPerGame}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-400">GA / GP</p>
                <p className="font-semibold text-white">{team.gaPerGame}</p>
              </div>
            </div>
          </div>

          {/* Home vs Away Splits */}
          <div className="rounded-xl border border-white/10 bg-[#0b0f17] p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-sky-400">
              Home vs. Away Win %
            </p>
            <div className="space-y-3 text-xs tabular-nums">
              <div>
                <div className="mb-1 flex justify-between text-white">
                  <span>Home ({team.homeRecord})</span>
                  <span>{team.homeWinPct}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className="h-full rounded-full bg-sky-400"
                    style={{ width: `${Math.min(team.homeWinPct, 100)}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="mb-1 flex justify-between text-white">
                  <span>Away ({team.awayRecord})</span>
                  <span>{team.awayWinPct}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className="h-full rounded-full bg-sky-300/70"
                    style={{ width: `${Math.min(team.awayWinPct, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Full Team Analytics Page Link */}
          <div className="flex flex-col justify-between rounded-xl border border-sky-500/25 bg-gradient-to-br from-sky-500/[0.1] via-[#0b0f17] to-[#0b0f17] p-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-sky-400">
                Full Team Profile
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-zinc-400">
                Explore {team.teamName} advanced 5v5 possession, special teams,
                NHL EDGE tracking, roster stats, schedule, and prospects.
              </p>
            </div>

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSelectTeam(team.teamAbbrev);
              }}
              className="group mt-4 flex w-full items-center justify-between rounded-xl border border-sky-400/50 bg-sky-500/15 px-4 py-2.5 text-sm font-semibold text-sky-300 shadow-[0_0_20px_rgba(56,189,248,0.16)] transition-all hover:bg-sky-500/25 hover:text-white"
            >
              <span>View {team.teamCommonName} Page</span>
              <span className="text-sky-400 transition-transform duration-200 group-hover:translate-x-1">
                →
              </span>
            </button>
          </div>
        </div>
      </td>
    </tr>
  );
}
