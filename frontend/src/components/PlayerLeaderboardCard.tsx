import type {
  GoalieStatRow,
  PlayerCategoryKey,
  SkaterStatRow,
} from "../types/players";
import PlayerAvatar from "./PlayerAvatar";

interface PlayerLeaderboardCardProps {
  category: PlayerCategoryKey;
  title: string;
  primaryStatLabel: string;
  skaters?: SkaterStatRow[];
  goalies?: GoalieStatRow[];
  wide?: boolean;
  onViewAll: (category: PlayerCategoryKey) => void;
  onSelectPlayer: (playerId: number) => void;
}

export default function PlayerLeaderboardCard({
  category,
  title,
  primaryStatLabel,
  skaters = [],
  goalies = [],
  wide = false,
  onViewAll,
  onSelectPlayer,
}: PlayerLeaderboardCardProps) {
  const isGoalies = category === "goalies";
  const isEmpty = isGoalies ? goalies.length === 0 : skaters.length === 0;

  return (
    <section
      className={`group/card relative flex flex-col overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17] shadow-[0_14px_45px_rgba(0,0,0,0.7)] transition-all duration-300 hover:border-sky-400/40 hover:shadow-[0_16px_50px_rgba(56,189,248,0.09)] ${
        wide ? "lg:col-span-2" : ""
      }`}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent" />

      {/* Clean Card Header (no subtext, no Top 5 pill) */}
      <div className="border-b border-white/10 bg-gradient-to-r from-sky-500/[0.11] via-sky-500/[0.03] to-transparent px-5 py-4">
        <h2 className="text-lg font-bold tracking-tight text-white">{title}</h2>
      </div>

      {/* Column Subheader */}
      <div className="grid grid-cols-[1fr_auto] items-center border-b border-white/5 bg-black/35 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
        <span>Player</span>
        <div className="flex items-center gap-4 text-right sm:gap-6">
          {isGoalies ? (
            <>
              <span className="hidden w-10 sm:inline">GP</span>
              <span className="hidden w-20 sm:inline">W-L-OTL</span>
              <span className="hidden w-12 md:inline">GAA</span>
              <span className="hidden w-10 md:inline">SO</span>
              <span className="w-14 text-sky-400">{primaryStatLabel}</span>
            </>
          ) : (
            <>
              <span className="hidden w-9 sm:inline">GP</span>
              <span className="hidden w-9 sm:inline">
                {category === "goals" ? "PTS" : "G"}
              </span>
              <span className="hidden w-9 sm:inline">A</span>
              <span className="w-12 text-sky-400">{primaryStatLabel}</span>
            </>
          )}
        </div>
      </div>

      {/* Top 5 Clickable Rows */}
      <div className="flex-1 divide-y divide-white/5">
        {isEmpty && (
          <div className="px-5 py-10 text-center text-sm text-zinc-500">
            No player stats available yet for this category.
          </div>
        )}

        {!isGoalies &&
          skaters.slice(0, 5).map((player) => {
            const isFirst = player.rank === 1;
            const primaryValue =
              category === "goals" ? player.goals : player.points;
            const secondaryValue =
              category === "goals" ? player.points : player.goals;

            return (
              <button
                key={player.playerId}
                type="button"
                onClick={() => onSelectPlayer(player.playerId)}
                className={`group/row grid w-full grid-cols-[1fr_auto] items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-sky-500/[0.08] ${
                  isFirst
                    ? "bg-gradient-to-r from-sky-500/[0.11] via-sky-500/[0.04] to-transparent"
                    : ""
                }`}
              >
                <div className="flex min-w-0 items-center gap-3.5">
                  <span
                    className={`w-5 text-center text-xs font-bold tabular-nums ${
                      isFirst
                        ? "text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.6)]"
                        : "text-zinc-500"
                    }`}
                  >
                    {player.rank}
                  </span>

                  <PlayerAvatar
                    src={player.headshotUrl}
                    name={player.fullName}
                    isLeader={isFirst}
                  />

                  <div className="min-w-0">
                    <p className="truncate font-semibold text-white transition-colors group-hover/row:text-sky-300">
                      {player.fullName}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-zinc-400">
                      {player.teamLogo && (
                        <img
                          src={player.teamLogo}
                          alt={player.teamAbbrev}
                          className="h-4 w-4 object-contain"
                          loading="lazy"
                        />
                      )}
                      <span className="font-medium text-zinc-300">
                        {player.teamAbbrev}
                      </span>
                      <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
                        {player.position}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-right text-sm tabular-nums sm:gap-6">
                  <span className="hidden w-9 text-white sm:inline">
                    {player.gp}
                  </span>
                  <span className="hidden w-9 text-white sm:inline">
                    {secondaryValue}
                  </span>
                  <span className="hidden w-9 text-white sm:inline">
                    {player.assists}
                  </span>
                  <span className="w-12 text-base font-bold text-sky-400 drop-shadow-[0_0_10px_rgba(56,189,248,0.45)]">
                    {primaryValue}
                  </span>
                </div>
              </button>
            );
          })}

        {isGoalies &&
          goalies.slice(0, 5).map((goalie) => {
            const isFirst = goalie.rank === 1;
            return (
              <button
                key={goalie.playerId}
                type="button"
                onClick={() => onSelectPlayer(goalie.playerId)}
                className={`group/row grid w-full grid-cols-[1fr_auto] items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-sky-500/[0.08] ${
                  isFirst
                    ? "bg-gradient-to-r from-sky-500/[0.11] via-sky-500/[0.04] to-transparent"
                    : ""
                }`}
              >
                <div className="flex min-w-0 items-center gap-3.5">
                  <span
                    className={`w-5 text-center text-xs font-bold tabular-nums ${
                      isFirst
                        ? "text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.6)]"
                        : "text-zinc-500"
                    }`}
                  >
                    {goalie.rank}
                  </span>

                  <PlayerAvatar
                    src={goalie.headshotUrl}
                    name={goalie.fullName}
                    isLeader={isFirst}
                  />

                  <div className="min-w-0">
                    <p className="truncate font-semibold text-white transition-colors group-hover/row:text-sky-300">
                      {goalie.fullName}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-zinc-400">
                      {goalie.teamLogo && (
                        <img
                          src={goalie.teamLogo}
                          alt={goalie.teamAbbrev}
                          className="h-4 w-4 object-contain"
                          loading="lazy"
                        />
                      )}
                      <span className="font-medium text-zinc-300">
                        {goalie.teamAbbrev}
                      </span>
                      <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
                        G
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-right text-sm tabular-nums sm:gap-6">
                  <span className="hidden w-10 text-white sm:inline">
                    {goalie.gp}
                  </span>
                  <span className="hidden w-20 text-white sm:inline">
                    {goalie.record}
                  </span>
                  <span className="hidden w-12 text-white md:inline">
                    {goalie.gaa.toFixed(2)}
                  </span>
                  <span className="hidden w-10 text-white md:inline">
                    {goalie.shutouts}
                  </span>
                  <span className="w-14 text-base font-bold text-sky-400 drop-shadow-[0_0_10px_rgba(56,189,248,0.45)]">
                    {goalie.savePctDisplay}
                  </span>
                </div>
              </button>
            );
          })}
      </div>

      {/* Bottom "Click to view all ->" Footer */}
      <button
        type="button"
        onClick={() => onViewAll(category)}
        className="group/btn flex w-full items-center justify-between border-t border-sky-500/15 bg-gradient-to-r from-black/50 via-sky-500/[0.04] to-black/50 px-5 py-3.5 text-sm font-semibold text-sky-300 transition-all hover:bg-sky-500/15 hover:text-sky-200"
      >
        <span>Click to view all</span>
        <span className="inline-flex items-center gap-1 text-sky-400 transition-transform duration-200 group-hover/btn:translate-x-1">
          →
        </span>
      </button>
    </section>
  );
}
