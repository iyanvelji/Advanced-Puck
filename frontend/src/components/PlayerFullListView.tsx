import { useEffect, useMemo, useState } from "react";
import { fetchPlayerCategory } from "../api/players";
import type {
  GoalieStatRow,
  PlayerCategoryKey,
  PlayerCategoryResponse,
  SkaterStatRow,
} from "../types/players";
import PlayerAvatar from "./PlayerAvatar";

interface PlayerFullListViewProps {
  category: PlayerCategoryKey;
  title: string;
  onBack: () => void;
  onSelectPlayer: (playerId: number) => void;
}

type SkaterSortKey =
  | "rank"
  | "gp"
  | "goals"
  | "assists"
  | "points"
  | "plusMinus"
  | "shots"
  | "shootingPct"
  | "ppPoints"
  | "pointsPerGame";

type GoalieSortKey =
  | "rank"
  | "gp"
  | "wins"
  | "losses"
  | "otLosses"
  | "savePct"
  | "gaa"
  | "shutouts"
  | "saves";

export default function PlayerFullListView({
  category,
  title,
  onBack,
  onSelectPlayer,
}: PlayerFullListViewProps) {
  const [data, setData] = useState<PlayerCategoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [qualifiedOnly, setQualifiedOnly] = useState(true);

  const [skaterSort, setSkaterSort] = useState<{
    key: SkaterSortKey;
    dir: "asc" | "desc";
  }>({ key: "rank", dir: "asc" });

  const [goalieSort, setGoalieSort] = useState<{
    key: GoalieSortKey;
    dir: "asc" | "desc";
  }>({ key: "rank", dir: "asc" });

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");

    fetchPlayerCategory(category, qualifiedOnly)
      .then((res) => {
        if (!ignore) setData(res);
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(
            err instanceof Error ? err.message : "Failed to load full list",
          );
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [category, qualifiedOnly]);

  const query = search.trim().toLowerCase();

  const filteredSkaters = useMemo(() => {
    const list: SkaterStatRow[] = (data?.skaters ?? []).filter(
      (p) =>
        !query ||
        p.fullName.toLowerCase().includes(query) ||
        p.teamAbbrevs.toLowerCase().includes(query),
    );
    return [...list].sort((a, b) =>
      skaterSort.dir === "asc"
        ? a[skaterSort.key] - b[skaterSort.key]
        : b[skaterSort.key] - a[skaterSort.key],
    );
  }, [data, query, skaterSort]);

  const filteredGoalies = useMemo(() => {
    const list: GoalieStatRow[] = (data?.goalies ?? []).filter(
      (g) =>
        !query ||
        g.fullName.toLowerCase().includes(query) ||
        g.teamAbbrevs.toLowerCase().includes(query),
    );
    return [...list].sort((a, b) =>
      goalieSort.dir === "asc"
        ? a[goalieSort.key] - b[goalieSort.key]
        : b[goalieSort.key] - a[goalieSort.key],
    );
  }, [data, query, goalieSort]);

  const toggleSkaterSort = (key: SkaterSortKey) => {
    setSkaterSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { key, dir: key === "rank" ? "asc" : "desc" },
    );
  };

  const toggleGoalieSort = (key: GoalieSortKey) => {
    setGoalieSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { key, dir: key === "gaa" || key === "rank" ? "asc" : "desc" },
    );
  };

  const isGoalies = category === "goalies";
  const primarySkaterKey = category === "goals" ? "goals" : "points";

  return (
    <div className="space-y-6">
      {/* Top Action & Filter Bar */}
      <div className="relative overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-5 sm:p-6">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent" />

        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={onBack}
              className="rounded-xl border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-300 transition hover:bg-sky-500/20"
            >
              ← Back to Leaders
            </button>
            <div>
              <p className="text-xs uppercase tracking-widest text-sky-400">
                {data?.seasonLabel || "Current Season"} · Full Leaderboard
              </p>
              <h1 className="mt-0.5 text-xl font-bold text-white sm:text-2xl">
                {title}
              </h1>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {isGoalies && (
              <button
                type="button"
                onClick={() => setQualifiedOnly((prev) => !prev)}
                className={`rounded-xl border px-3.5 py-2 text-xs font-semibold transition ${
                  qualifiedOnly
                    ? "border-sky-400/50 bg-sky-500/15 text-sky-300"
                    : "border-white/10 bg-black/40 text-zinc-400 hover:text-white"
                }`}
              >
                {qualifiedOnly
                  ? `Qualified Only (Min ${data?.goalieMinGp ?? 1} GP)`
                  : "Showing All Goalies"}
              </button>
            )}

            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search players..."
              className="w-56 rounded-xl border border-white/10 bg-[#05070a] px-3.5 py-2 text-sm text-white placeholder-zinc-500 focus:border-sky-400 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {loading && (
        <div className="rounded-2xl border border-white/10 bg-[#0b0f17] p-12 text-center text-sm text-zinc-400">
          Loading full {title.toLowerCase()} leaderboard...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-2xl border border-red-500/30 bg-red-950/20 p-6 text-sm text-red-200">
          {error}
        </div>
      )}

      {!loading && !error && !isGoalies && (
        <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-white/10 bg-black/45 text-xs uppercase tracking-wider text-zinc-400">
                  <th
                    onClick={() => toggleSkaterSort("rank")}
                    className="cursor-pointer py-3.5 pl-5 pr-3 font-medium hover:text-white"
                  >
                    #
                  </th>
                  <th className="px-3 py-3.5 font-medium">Player</th>
                  {(
                    [
                      ["gp", "GP"],
                      ["goals", "G"],
                      ["assists", "A"],
                      ["points", "PTS"],
                      ["plusMinus", "+/-"],
                      ["shots", "SOG"],
                      ["shootingPct", "S%"],
                      ["ppPoints", "PPP"],
                      ["pointsPerGame", "P/GP"],
                    ] as [SkaterSortKey, string][]
                  ).map(([key, label]) => (
                    <th
                      key={key}
                      onClick={() => toggleSkaterSort(key)}
                      className={`cursor-pointer select-none px-3 py-3.5 text-center font-medium transition hover:text-white ${
                        key === primarySkaterKey
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
                  <th className="px-3 py-3.5 pr-5 text-center font-medium">
                    TOI/G
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-white/5 text-sm tabular-nums">
                {filteredSkaters.map((player) => (
                  <tr
                    key={player.playerId}
                    onClick={() => onSelectPlayer(player.playerId)}
                    className="cursor-pointer transition-colors hover:bg-sky-500/[0.08]"
                  >
                    <td className="py-3 pl-5 pr-3 text-xs font-semibold text-zinc-500">
                      {player.rank}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-3">
                        <PlayerAvatar
                          src={player.headshotUrl}
                          name={player.fullName}
                          size="sm"
                          isLeader={player.rank === 1}
                        />
                        <div>
                          <p className="font-medium text-white">
                            {player.fullName}
                          </p>
                          <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
                            {player.teamLogo && (
                              <img
                                src={player.teamLogo}
                                alt={player.teamAbbrev}
                                className="h-3.5 w-3.5 object-contain"
                                loading="lazy"
                              />
                            )}
                            <span>{player.teamAbbrevs}</span>
                            <span>·</span>
                            <span>{player.position}</span>
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {player.gp}
                    </td>
                    <td
                      className={`px-3 py-3 text-center ${
                        primarySkaterKey === "goals"
                          ? "font-bold text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.4)]"
                          : "text-white"
                      }`}
                    >
                      {player.goals}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {player.assists}
                    </td>
                    <td
                      className={`px-3 py-3 text-center ${
                        primarySkaterKey === "points"
                          ? "font-bold text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.4)]"
                          : "text-white"
                      }`}
                    >
                      {player.points}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {player.plusMinus > 0
                        ? `+${player.plusMinus}`
                        : player.plusMinus}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {player.shots}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {player.shootingPct.toFixed(1)}%
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {player.ppPoints}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {player.pointsPerGame.toFixed(2)}
                    </td>
                    <td className="px-3 py-3 pr-5 text-center text-white">
                      {player.toiPerGame}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {!loading && !error && isGoalies && (
        <section className="overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)]">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-white/10 bg-black/45 text-xs uppercase tracking-wider text-zinc-400">
                  <th
                    onClick={() => toggleGoalieSort("rank")}
                    className="cursor-pointer py-3.5 pl-5 pr-3 font-medium hover:text-white"
                  >
                    #
                  </th>
                  <th className="px-3 py-3.5 font-medium">Goalie</th>
                  {(
                    [
                      ["gp", "GP"],
                      ["wins", "W"],
                      ["losses", "L"],
                      ["otLosses", "OTL"],
                      ["savePct", "SV%"],
                      ["gaa", "GAA"],
                      ["shutouts", "SO"],
                      ["saves", "SV"],
                    ] as [GoalieSortKey, string][]
                  ).map(([key, label]) => (
                    <th
                      key={key}
                      onClick={() => toggleGoalieSort(key)}
                      className={`cursor-pointer select-none px-3 py-3.5 text-center font-medium transition hover:text-white ${
                        key === "savePct" ? "font-semibold text-sky-400" : ""
                      }`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {label}
                        {goalieSort.key === key && (
                          <span className="text-[10px] text-sky-400">
                            {goalieSort.dir === "asc" ? "▲" : "▼"}
                          </span>
                        )}
                      </span>
                    </th>
                  ))}
                  <th className="px-3 py-3.5 pr-5 text-center font-medium">
                    SA
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-white/5 text-sm tabular-nums">
                {filteredGoalies.map((goalie) => (
                  <tr
                    key={goalie.playerId}
                    onClick={() => onSelectPlayer(goalie.playerId)}
                    className="cursor-pointer transition-colors hover:bg-sky-500/[0.08]"
                  >
                    <td className="py-3 pl-5 pr-3 text-xs font-semibold text-zinc-500">
                      {goalie.rank}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-3">
                        <PlayerAvatar
                          src={goalie.headshotUrl}
                          name={goalie.fullName}
                          size="sm"
                          isLeader={goalie.rank === 1}
                        />
                        <div>
                          <p className="font-medium text-white">
                            {goalie.fullName}
                          </p>
                          <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
                            {goalie.teamLogo && (
                              <img
                                src={goalie.teamLogo}
                                alt={goalie.teamAbbrev}
                                className="h-3.5 w-3.5 object-contain"
                                loading="lazy"
                              />
                            )}
                            <span>{goalie.teamAbbrevs}</span>
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {goalie.gp}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {goalie.wins}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {goalie.losses}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {goalie.otLosses}
                    </td>
                    <td className="px-3 py-3 text-center font-bold text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.4)]">
                      {goalie.savePctDisplay}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {goalie.gaa.toFixed(2)}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {goalie.shutouts}
                    </td>
                    <td className="px-3 py-3 text-center text-white">
                      {goalie.saves}
                    </td>
                    <td className="px-3 py-3 pr-5 text-center text-white">
                      {goalie.shotsAgainst}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
