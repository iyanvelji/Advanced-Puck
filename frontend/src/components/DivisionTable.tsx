import { Fragment, useMemo, useState } from "react";
import type { TeamStanding } from "../types/standings";
import TeamDetailDrawer from "./TeamDetailDrawer";

type ColumnKey =
  | "gp"
  | "w"
  | "l"
  | "otl"
  | "pts"
  | "gf"
  | "ga"
  | "diff"
  | "l10"
  | "strk";

type SortKey = ColumnKey | "divisionSequence";
type SortDirection = "asc" | "desc";

interface SortConfig {
  key: SortKey;
  direction: SortDirection;
}

interface DivisionTableProps {
  divisionName: string;
  teams: TeamStanding[];
  onSelectTeam: (teamAbbrev: string) => void;
}

const COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: "gp", label: "GP" },
  { key: "w", label: "W" },
  { key: "l", label: "L" },
  { key: "otl", label: "OTL" },
  { key: "pts", label: "Pts" },
  { key: "gf", label: "GF" },
  { key: "ga", label: "GA" },
  { key: "diff", label: "Diff" },
  { key: "l10", label: "L10" },
  { key: "strk", label: "Strk" },
];

export default function DivisionTable({
  divisionName,
  teams,
  onSelectTeam,
}: DivisionTableProps) {
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    key: "divisionSequence",
    direction: "asc",
  });
  const [expandedAbbrev, setExpandedAbbrev] = useState<string | null>(null);

  const isDefaultSort =
    sortConfig.key === "divisionSequence" && sortConfig.direction === "asc";

  const sortedTeams = useMemo(() => {
    const copy = [...teams];
    copy.sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];

      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortConfig.direction === "asc"
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortConfig.direction === "asc" ? aVal - bVal : bVal - aVal;
      }

      return 0;
    });
    return copy;
  }, [teams, sortConfig]);

  const handleSort = (key: ColumnKey) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        return {
          key,
          direction: prev.direction === "desc" ? "asc" : "desc",
        };
      }
      return { key, direction: "desc" };
    });
  };

  const resetSort = () => {
    setSortConfig({ key: "divisionSequence", direction: "asc" });
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_12px_40px_rgba(0,0,0,0.65)]">
      {/* Division Card Header */}
      <div className="flex items-center justify-between border-b border-white/10 bg-gradient-to-r from-sky-500/10 via-transparent to-transparent px-5 py-4">
        <h2 className="text-lg font-bold tracking-tight text-white">
          {divisionName} Division
        </h2>

        {!isDefaultSort && (
          <button
            type="button"
            onClick={resetSort}
            className="rounded-lg border border-sky-400/40 bg-sky-500/10 px-3 py-1 text-xs font-medium text-sky-300 transition hover:bg-sky-500/20"
          >
            Reset to Standings
          </button>
        )}
      </div>

      {/* Standings Table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-white/10 bg-black/40 text-xs uppercase tracking-wider text-zinc-400">
              <th className="py-3.5 pl-5 pr-4 font-medium">Team</th>
              {COLUMNS.map((col) => {
                const isSorted = sortConfig.key === col.key;
                return (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className={`cursor-pointer select-none px-3 py-3.5 text-center font-medium transition hover:text-white ${
                      col.key === "pts" ? "font-semibold text-sky-400" : ""
                    }`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label}
                      {isSorted && (
                        <span className="text-[10px] text-sky-400">
                          {sortConfig.direction === "asc" ? "▲" : "▼"}
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>

          <tbody className="divide-y divide-white/5 text-sm tabular-nums">
            {sortedTeams.map((team, idx) => {
              const isExpanded = expandedAbbrev === team.teamAbbrev;
              const showPlayoffCutoff = isDefaultSort && idx === 2;

              return (
                <Fragment key={team.teamAbbrev}>
                  <tr
                    onClick={() =>
                      setExpandedAbbrev(isExpanded ? null : team.teamAbbrev)
                    }
                    className={`cursor-pointer transition-colors hover:bg-sky-500/[0.06] ${
                      isExpanded ? "bg-sky-500/[0.08]" : ""
                    } ${
                      showPlayoffCutoff
                        ? "border-b-2 border-dashed border-sky-400/35"
                        : ""
                    }`}
                  >
                    <td className="py-3.5 pl-5 pr-4">
                      <div className="flex items-center gap-3">
                        <span className="w-4 text-xs text-zinc-500">
                          {team.divisionSequence}
                        </span>
                        {team.teamLogo ? (
                          <img
                            src={team.teamLogo}
                            alt={team.teamCommonName}
                            className="h-7 w-7 object-contain"
                            loading="lazy"
                          />
                        ) : (
                          <div className="flex h-7 w-7 items-center justify-center rounded-full border border-sky-400/30 bg-black text-[10px] font-bold text-white">
                            {team.teamAbbrev}
                          </div>
                        )}
                        <span className="font-medium text-white">
                          {team.teamCommonName}
                        </span>
                      </div>
                    </td>

                    <td className="px-3 py-3.5 text-center text-white">
                      {team.gp}
                    </td>
                    <td className="px-3 py-3.5 text-center text-white">
                      {team.w}
                    </td>
                    <td className="px-3 py-3.5 text-center text-white">
                      {team.l}
                    </td>
                    <td className="px-3 py-3.5 text-center text-white">
                      {team.otl}
                    </td>

                    {/* Points highlighted in light blue */}
                    <td className="px-3 py-3.5 text-center font-bold text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.35)]">
                      {team.pts}
                    </td>

                    <td className="px-3 py-3.5 text-center text-white">
                      {team.gf}
                    </td>
                    <td className="px-3 py-3.5 text-center text-white">
                      {team.ga}
                    </td>
                    <td className="px-3 py-3.5 text-center text-white">
                      {team.diff > 0 ? `+${team.diff}` : team.diff}
                    </td>
                    <td className="px-3 py-3.5 text-center text-white">
                      {team.l10}
                    </td>
                    <td className="px-3 py-3.5 text-center text-white">
                      {team.strk}
                    </td>
                  </tr>

                  {isExpanded && (
                    <TeamDetailDrawer team={team} onSelectTeam={onSelectTeam} />
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
