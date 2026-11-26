export interface TeamStatItem {
  label: string;
  value: string;
  rank?: string | null;
  highlight?: boolean;
}

export interface TeamStatGroup {
  title: string;
  items: TeamStatItem[];
}

export interface PeriodScoringRow {
  period: string;
  gf: number;
  ga: number;
  diff: number;
}

export interface TeamEdgeMetric {
  label: string;
  value: string;
  rank: number | null;
  percentile: number | null;
  leagueAvg: string | null;
}

export interface TeamEdgeZones {
  offensive: number;
  neutral: number;
  defensive: number;
  offensiveRank: number | null;
  offensiveLeagueAvg: number | null;
}

export interface TeamEdgeShotLocation {
  zone: string;
  shots: number;
  goals: number;
  shootingPct: string;
  shotsRank: number | null;
  leagueAvgPct: string | null;
}

export interface TeamEdgeData {
  metrics: TeamEdgeMetric[];
  zones: TeamEdgeZones | null;
  shotLocations: TeamEdgeShotLocation[];
}

export interface TeamSkaterRow {
  playerId: number;
  fullName: string;
  headshotUrl: string;
  sweaterNumber: number | null;
  position: string;
  gp: number;
  goals: number;
  assists: number;
  points: number;
  plusMinus: number;
  pim: number;
  ppGoals: number;
  shGoals: number;
  gwg: number;
  shots: number;
  shootingPct: number;
  toiPerGame: string;
  faceoffWinPct: string;
}

export interface TeamGoalieRow {
  playerId: number;
  fullName: string;
  headshotUrl: string;
  sweaterNumber: number | null;
  gp: number;
  gs: number;
  wins: number;
  losses: number;
  otLosses: number;
  record: string;
  savePct: number;
  savePctDisplay: string;
  gaa: number;
  shutouts: number;
  saves: number;
  shotsAgainst: number;
}

export interface RosterPerson {
  playerId: number | null;
  fullName: string;
  sweaterNumber: number | null;
  position: string;
  headshotUrl: string;
  shootsCatches: string;
  height: string;
  weight: string;
  age: number | null;
  birthplace: string;
}

export interface TeamGameItem {
  gameId: number;
  date: string;
  isHome: boolean;
  opponentAbbrev: string;
  opponentLogo: string;
  venue: string;
  gameState: string;
  startTimeUTC: string;
  teamScore: number | null;
  opponentScore: number | null;
  periodType: string;
  result: string;
}

export interface TeamProfileResponse {
  teamAbbrev: string;
  teamId: number | null;
  seasonId: string;
  seasonLabel: string;
  header: {
    teamName: string;
    teamCommonName: string;
    teamLogo: string;
    conferenceName: string;
    divisionName: string;
    divisionRank: string | null;
    leagueRank: string | null;
    homeRecord: string;
    awayRecord: string;
    l10: string;
    streak: string;
  };
  headlineKpis: TeamStatItem[];
  statGroups: TeamStatGroup[];
  periodScoring: PeriodScoringRow[];
  edge: TeamEdgeData | null;
  skaters: TeamSkaterRow[];
  goalies: TeamGoalieRow[];
  roster: {
    forwards: RosterPerson[];
    defensemen: RosterPerson[];
    goalies: RosterPerson[];
  };
  recentGames: TeamGameItem[];
  upcomingGames: TeamGameItem[];
  prospects: {
    forwards: RosterPerson[];
    defensemen: RosterPerson[];
    goalies: RosterPerson[];
  };
  moneyPuck?: TeamMoneyPuckData | null;
}

import type {
  ExpectedVsActualRow,
  MoneyPuckSituationKey,
  RadarAxisPoint,
} from "./players";

export interface TeamDangerComparisonPoint {
  zone: string;
  shotsFor: number;
  shotsAgainst: number;
  xGF: number;
  xGA: number;
  goalsFor: number;
  goalsAgainst: number;
}

export interface SituationalDominancePoint {
  situation: string;
  xgPct: number;
  corsiPct: number;
  fenwickPct: number;
}

export interface TeamMoneyPuckSituation {
  statGroups: TeamStatGroup[];
  charts: {
    radar: RadarAxisPoint[];
    dangerComparison: TeamDangerComparisonPoint[];
    expectedVsActual: ExpectedVsActualRow[];
  };
}

export interface TeamMoneyPuckData {
  source: string;
  defaultSituation: MoneyPuckSituationKey;
  situations: Partial<Record<MoneyPuckSituationKey, TeamMoneyPuckSituation>>;
  situationalDominance: SituationalDominancePoint[];
}
