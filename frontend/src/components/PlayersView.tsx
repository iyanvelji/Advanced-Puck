import { useEffect, useRef, useState } from "react";
import { fetchPlayerLeaders, searchPlayers } from "../api/players";
import type {
  PlayerCategoryKey,
  PlayerSearchItem,
  PlayersLeadersResponse,
} from "../types/players";
import PlayerAvatar from "./PlayerAvatar";
import PlayerLeaderboardCard from "./PlayerLeaderboardCard";
import PlayerFullListView from "./PlayerFullListView";
import PlayerDetailView from "./PlayerDetailView";
import DonateBanner from "./DonateBanner";

interface PlayersViewProps {
  onBackToTeams?: () => void;
  onOpenDonate?: () => void;
}

const CATEGORY_TITLES: Record<PlayerCategoryKey, string> = {
  points: "Top Point Scorers",
  goals: "Top Goal Scorers",
  goalies: "Top Goalies",
  defensemen: "Top Defensemen by Points",
  rookies: "Top Rookies by Points",
};

export default function PlayersView({
  onBackToTeams,
  onOpenDonate,
}: PlayersViewProps) {
  const [data, setData] = useState<PlayersLeadersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeCategory, setActiveCategory] =
    useState<PlayerCategoryKey | null>(null);
  const [selectedPlayerId, setSelectedPlayerId] = useState<number | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<PlayerSearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const searchBoxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");

    fetchPlayerLeaders()
      .then((res) => {
        if (!ignore) setData(res);
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load player leaders",
          );
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  // Debounced player search
  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (trimmed.length < 2) {
      setSearchResults([]);
      setSearching(false);
      return;
    }

    let ignore = false;
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchPlayers(trimmed)
        .then((res) => {
          if (!ignore) setSearchResults(res.results);
        })
        .catch(() => {
          if (!ignore) setSearchResults([]);
        })
        .finally(() => {
          if (!ignore) setSearching(false);
        });
    }, 200);

    return () => {
      ignore = true;
      window.clearTimeout(timer);
    };
  }, [searchQuery]);

  // Close search dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        searchBoxRef.current &&
        !searchBoxRef.current.contains(event.target as Node)
      ) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleOpenPlayer = (playerId: number) => {
    setDropdownOpen(false);
    setSelectedPlayerId(playerId);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (selectedPlayerId !== null) {
    return (
      <PlayerDetailView
        playerId={selectedPlayerId}
        backLabel={
          activeCategory
            ? `Back to ${CATEGORY_TITLES[activeCategory]}`
            : "Back to Player Stats"
        }
        onBack={() => setSelectedPlayerId(null)}
      />
    );
  }

  if (activeCategory) {
    return (
      <PlayerFullListView
        category={activeCategory}
        title={CATEGORY_TITLES[activeCategory]}
        onBack={() => setActiveCategory(null)}
        onSelectPlayer={handleOpenPlayer}
      />
    );
  }

  const hasPlayers =
    (data?.topPoints?.length ?? 0) > 0 || (data?.topGoalies?.length ?? 0) > 0;

  return (
    <div className="space-y-8">
      {onOpenDonate && <DonateBanner onOpenDonate={onOpenDonate} />}

      {/* Header Banner: "Player Stats" + Live Search Bar */}
      <div className="relative z-20 rounded-2xl border border-sky-500/20 bg-[#0b0f17] px-5 py-5 sm:px-6">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px rounded-t-2xl bg-gradient-to-r from-transparent via-sky-400/60 to-transparent" />

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Player Stats
          </h1>

          {/* Player Search Bar */}
          <div ref={searchBoxRef} className="relative w-full sm:w-80">
            <div className="relative flex items-center">
              <svg
                className="pointer-events-none absolute left-3.5 h-4 w-4 text-sky-400/80"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="m21 21-4.35-4.35M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0Z"
                />
              </svg>
              <input
                type="text"
                value={searchQuery}
                onFocus={() => setDropdownOpen(true)}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setDropdownOpen(true);
                }}
                placeholder="Search players..."
                className="w-full rounded-xl border border-sky-500/25 bg-[#05070a] py-2.5 pl-10 pr-9 text-sm text-white placeholder-zinc-500 transition focus:border-sky-400 focus:shadow-[0_0_18px_rgba(56,189,248,0.18)] focus:outline-none"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery("");
                    setSearchResults([]);
                  }}
                  className="absolute right-3 text-sm text-zinc-400 hover:text-white"
                  aria-label="Clear search"
                >
                  ×
                </button>
              )}
            </div>

            {/* Live Search Dropdown */}
            {dropdownOpen && searchQuery.trim().length >= 2 && (
              <div className="absolute right-0 mt-2 max-h-96 w-full overflow-y-auto rounded-xl border border-sky-500/30 bg-[#070b12] shadow-[0_20px_50px_rgba(0,0,0,0.85)]">
                {searching && (
                  <div className="px-4 py-4 text-center text-xs text-zinc-400">
                    Searching players...
                  </div>
                )}

                {!searching && searchResults.length === 0 && (
                  <div className="px-4 py-4 text-center text-xs text-zinc-500">
                    No players found matching "{searchQuery.trim()}"
                  </div>
                )}

                {!searching &&
                  searchResults.map((hit) => (
                    <button
                      key={hit.playerId}
                      type="button"
                      onClick={() => handleOpenPlayer(hit.playerId)}
                      className="flex w-full items-center justify-between gap-3 border-b border-white/5 px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-sky-500/15"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <PlayerAvatar
                          src={hit.headshotUrl}
                          name={hit.fullName}
                          size="sm"
                        />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-white">
                            {hit.fullName}
                          </p>
                          <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
                            {hit.teamLogo && (
                              <img
                                src={hit.teamLogo}
                                alt={hit.teamAbbrev}
                                className="h-3.5 w-3.5 object-contain"
                              />
                            )}
                            <span>{hit.teamAbbrev}</span>
                            <span>·</span>
                            <span>{hit.position}</span>
                          </div>
                        </div>
                      </div>
                      <span className="shrink-0 text-xs font-semibold text-sky-400 tabular-nums">
                        {hit.statSummary}
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Loading / Error / Empty States */}
      {loading && (
        <div className="rounded-2xl border border-white/10 bg-[#0b0f17] p-12 text-center text-sm text-zinc-400">
          Loading NHL player stats...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-2xl border border-red-500/30 bg-red-950/20 p-6 text-sm text-red-200">
          {error} — make sure Django is running on port 8000.
        </div>
      )}

      {!loading && !error && !hasPlayers && (
        <div className="rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-8 text-center text-sm text-zinc-300">
          No player stats found in your database yet. Run{" "}
          <code className="rounded bg-black px-2 py-1 text-sky-400">
            python manage.py ingest_players
          </code>{" "}
          in <code className="text-white">backend/</code> and refresh.
          {onBackToTeams && (
            <div className="mt-4">
              <button
                type="button"
                onClick={onBackToTeams}
                className="rounded-lg border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-xs font-semibold text-sky-300 transition hover:bg-sky-500/20"
              >
                ← Back to Teams Standings
              </button>
            </div>
          )}
        </div>
      )}

      {/* 5 Leaderboards Grid */}
      {!loading && !error && hasPlayers && data && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <PlayerLeaderboardCard
            category="points"
            title="Top Point Scorers"
            primaryStatLabel="PTS"
            skaters={data.topPoints}
            onViewAll={setActiveCategory}
            onSelectPlayer={handleOpenPlayer}
          />

          <PlayerLeaderboardCard
            category="goals"
            title="Top Goal Scorers"
            primaryStatLabel="G"
            skaters={data.topGoals}
            onViewAll={setActiveCategory}
            onSelectPlayer={handleOpenPlayer}
          />

          <PlayerLeaderboardCard
            category="goalies"
            title="Top Goalies"
            primaryStatLabel="SV%"
            goalies={data.topGoalies}
            wide
            onViewAll={setActiveCategory}
            onSelectPlayer={handleOpenPlayer}
          />

          <PlayerLeaderboardCard
            category="defensemen"
            title="Top Defensemen by Points"
            primaryStatLabel="PTS"
            skaters={data.topDefensemen}
            onViewAll={setActiveCategory}
            onSelectPlayer={handleOpenPlayer}
          />

          <PlayerLeaderboardCard
            category="rookies"
            title="Top Rookies by Points"
            primaryStatLabel="PTS"
            skaters={data.topRookies}
            onViewAll={setActiveCategory}
            onSelectPlayer={handleOpenPlayer}
          />
        </div>
      )}
    </div>
  );
}
