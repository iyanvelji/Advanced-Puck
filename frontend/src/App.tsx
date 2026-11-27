import { useEffect, useState } from "react";
import { fetchStandings } from "./api/standings";
import type {
  Conference,
  NavSection,
  StandingsResponse,
  TeamStanding,
} from "./types/standings";
import Navbar from "./components/Navbar";
import DivisionTable from "./components/DivisionTable";
import PlayersView from "./components/PlayersView";
import TeamDetailView from "./components/TeamDetailView";
import PlayerDetailView from "./components/PlayerDetailView";
import DonateBanner from "./components/DonateBanner";
import DonatePage from "./components/DonatePage";

const CONFERENCES: Conference[] = ["Eastern", "Western"];

export default function App() {
  const [activeSection, setActiveSection] = useState<NavSection>("teams");
  const [activeConference, setActiveConference] =
    useState<Conference>("Eastern");
  const [selectedTeamAbbrev, setSelectedTeamAbbrev] = useState<string | null>(
    null,
  );
  const [selectedPlayerFromTeam, setSelectedPlayerFromTeam] = useState<
    number | null
  >(null);
  const [showDonate, setShowDonate] = useState<boolean>(false);
  const [data, setData] = useState<StandingsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");

    fetchStandings()
      .then((res) => {
        if (!ignore) {
          setData(res);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(
            err instanceof Error ? err.message : "Failed to load standings",
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

  const handleSelectSection = (section: NavSection) => {
    setShowDonate(false);
    setActiveSection(section);
    setSelectedTeamAbbrev(null);
    setSelectedPlayerFromTeam(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleOpenDonate = () => {
    setShowDonate(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleOpenTeam = (teamAbbrev: string) => {
    setSelectedPlayerFromTeam(null);
    setSelectedTeamAbbrev(teamAbbrev);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleOpenPlayerFromTeam = (playerId: number) => {
    setSelectedPlayerFromTeam(playerId);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const conferenceDivisions: Record<string, TeamStanding[]> =
    data?.conferences?.[activeConference] ?? {};
  const divisionEntries = Object.entries(conferenceDivisions);
  const hasTeams = divisionEntries.some(([, teams]) => teams.length > 0);

  return (
    <div className="min-h-screen bg-[#05070a] flex-col text-white">
      <Navbar
        activeSection={activeSection}
        onSelectSection={handleSelectSection}
      />

      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
        {showDonate ? (
          <DonatePage onBack={() => setShowDonate(false)} />
        ) : activeSection === "players" ? (
          <PlayersView
            onBackToTeams={() => handleSelectSection("teams")}
            onOpenDonate={handleOpenDonate}
          />
        ) : selectedPlayerFromTeam !== null && selectedTeamAbbrev ? (
          <PlayerDetailView
            playerId={selectedPlayerFromTeam}
            backLabel={`Back to ${selectedTeamAbbrev} Team Page`}
            onBack={() => setSelectedPlayerFromTeam(null)}
          />
        ) : selectedTeamAbbrev ? (
          <TeamDetailView
            teamAbbrev={selectedTeamAbbrev}
            onBack={() => setSelectedTeamAbbrev(null)}
            onSelectPlayer={handleOpenPlayerFromTeam}
          />
        ) : (
          <>
            <DonateBanner onOpenDonate={handleOpenDonate} className="mb-8" />
            {/* Current Season + Conference Tabs */}
            <div className="mb-8 overflow-hidden rounded-2xl border border-sky-500/20 bg-[#0b0f17]">
              <div className="border-b border-white/10 px-5 py-4">
                <p className="text-xs uppercase tracking-wider text-zinc-400">
                  Season
                </p>
                <p className="mt-1 text-lg font-bold tracking-tight text-white">
                  {data?.seasonLabel || "—"}
                </p>
              </div>

              {/* Eastern / Western Conference Switcher */}
              <div className="grid grid-cols-2">
                {CONFERENCES.map((conf) => {
                  const isActive = activeConference === conf;
                  return (
                    <button
                      key={conf}
                      type="button"
                      onClick={() => setActiveConference(conf)}
                      className={`relative py-4 text-center text-sm font-semibold transition sm:text-base ${
                        isActive
                          ? "bg-sky-500/10 text-white"
                          : "text-zinc-400 hover:bg-white/[0.03] hover:text-zinc-200"
                      }`}
                    >
                      {conf} Conference
                      {isActive && (
                        <span className="absolute inset-x-0 bottom-0 h-0.5 bg-sky-400 shadow-[0_0_12px_#38bdf8]" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Content States */}
            {loading && (
              <div className="rounded-2xl border border-white/10 bg-[#0b0f17] p-10 text-center text-sm text-zinc-400">
                Loading {activeConference} Conference standings...
              </div>
            )}

            {!loading && error && (
              <div className="rounded-2xl border border-red-500/30 bg-red-950/20 p-6 text-sm text-red-200">
                {error} — make sure Django is running on port 8000.
              </div>
            )}

            {!loading && !error && !hasTeams && (
              <div className="rounded-2xl border border-sky-500/20 bg-[#0b0f17] p-8 text-center text-sm text-zinc-300">
                No standings found in your database yet. Run{" "}
                <code className="rounded bg-black px-2 py-1 text-sky-400">
                  python manage.py ingest_standings
                </code>{" "}
                in <code className="text-white">backend/</code> and refresh.
              </div>
            )}

            {!loading && !error && hasTeams && (
              <div className="space-y-8">
                {divisionEntries.map(([divisionName, teams]) => (
                  <DivisionTable
                    key={divisionName}
                    divisionName={divisionName}
                    teams={teams}
                    onSelectTeam={handleOpenTeam}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>
      <footer className="mx-auto w-full max-w-6xl border-t border-white/10 px-4 py-6 text-center text-xs text-zinc-500 sm:px-6 sm:text-right">
        Stats and advanced stats provided by{" "}
        <a
          href="https://moneypuck.com"
          target="_blank"
          rel="noreferrer"
          className="text-sky-400/90 underline hover:text-sky-300"
        >
          MoneyPuck.com
        </a>{" "}
        and{" "}
        <a
          href="https://www.nhl.com"
          target="_blank"
          rel="noreferrer"
          className="text-sky-400/90 underline hover:text-sky-300"
        >
          NHL.com
        </a>
        . Created by Iyan Velji
      </footer>
    </div>
  );
}
