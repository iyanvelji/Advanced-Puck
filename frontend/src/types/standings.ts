export type NavSection = "teams" | "players";
export type Conference = "Eastern" | "Western";

export interface TeamStanding {
  id: number;
  teamAbbrev: string;
  teamName: string;
  teamCommonName: string;
  teamLogo: string;
  conferenceName: string;
  divisionName: string;
  divisionSequence: number;
  gp: number;
  w: number;
  l: number;
  otl: number;
  pts: number;
  pointPctg: number;
  gf: number;
  ga: number;
  diff: number;
  l10: string;
  strk: string;
  homeRecord: string;
  awayRecord: string;
  homeWinPct: number;
  awayWinPct: number;
  gfPerGame: number;
  gaPerGame: number;
  diffPerGame: number;
}

export interface StandingsResponse {
  seasonId: string;
  seasonLabel: string;
  availableSeasons: string[];
  conferences: Record<Conference, Record<string, TeamStanding[]>>;
}
