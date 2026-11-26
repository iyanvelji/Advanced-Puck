export type PlayerCategoryKey =
  | "points"
  | "goals"
  | "goalies"
  | "defensemen"
  | "rookies";

export interface SkaterStatRow {
  rank: number;
  playerId: number;
  fullName: string;
  teamAbbrev: string;
  teamAbbrevs: string;
  position: string;
  isRookie: boolean;
  headshotUrl: string;
  teamLogo: string;
  gp: number;
  goals: number;
  assists: number;
  points: number;
  plusMinus: number;
  shots: number;
  shootingPct: number;
  ppPoints: number;
  pointsPerGame: number;
  toiPerGame: string;
}

export interface GoalieStatRow {
  rank: number;
  playerId: number;
  fullName: string;
  teamAbbrev: string;
  teamAbbrevs: string;
  headshotUrl: string;
  teamLogo: string;
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

export interface PlayersLeadersResponse {
  seasonId: string;
  seasonLabel: string;
  goalieMinGp: number;
  topPoints: SkaterStatRow[];
  topGoals: SkaterStatRow[];
  topGoalies: GoalieStatRow[];
  topDefensemen: SkaterStatRow[];
  topRookies: SkaterStatRow[];
}

export interface PlayerCategoryResponse {
  category: PlayerCategoryKey;
  seasonId: string;
  seasonLabel: string;
  goalieMinGp: number;
  totalCount: number;
  skaters: SkaterStatRow[];
  goalies: GoalieStatRow[];
}

export interface PlayerSearchItem {
  playerId: number;
  fullName: string;
  teamAbbrev: string;
  position: string;
  headshotUrl: string;
  teamLogo: string;
  statSummary: string;
}

export interface PlayerSearchResponse {
  query: string;
  results: PlayerSearchItem[];
}

export interface PlayerStatItem {
  label: string;
  value: string;
  highlight?: boolean;
}

export interface PlayerStatGroup {
  title: string;
  items: PlayerStatItem[];
}

export interface EdgeMetric {
  label: string;
  value: string;
  percentile: number | null;
  leagueAvg: string | null;
}

export interface EdgeZones {
  offensive: number;
  neutral: number;
  defensive: number;
  offensivePercentile: number | null;
}

export interface EdgeShotLocation {
  zone: string;
  shots: number;
  goals: number;
  shootingPct: string;
  percentile: number | null;
}

export interface PlayerEdgeData {
  metrics: EdgeMetric[];
  zones: EdgeZones | null;
  shotLocations: EdgeShotLocation[];
}

export interface PlayerGameLogEntry {
  gameId?: number;
  date: string;
  opponent: string;
  homeRoad: string;
  goals: number;
  assists: number;
  points: number;
  plusMinus: number;
  shots: number;
  pim: number;
  ppGoals: number;
  ppPoints: number;
  toi: string;
  decision: string;
  shotsAgainst: number | null;
  goalsAgainst: number | null;
  savePct: string;
  shutouts: number;
}

export interface PlayerSeasonRow {
  season: string;
  league: string;
  team: string;
  gameType: "Regular" | "Playoffs";
  gp: number;
  goals: number;
  assists: number;
  points: number;
  plusMinus: number | null;
  pim: number;
  shots: number | null;
  ppGoals: number | null;
  gwg: number | null;
  avgToi: string;
  wins: number | null;
  losses: number | null;
  otLosses: number | null;
  gaa: number | null;
  savePct: string;
  shutouts: number | null;
}

export interface PlayerAward {
  trophy: string;
  seasons: string[];
  count: number;
}

export interface PlayerProfileResponse {
  playerId: number;
  seasonId: string;
  seasonLabel: string;
  isGoalie: boolean;
  bio: {
    fullName: string;
    sweaterNumber: number | null;
    position: string;
    teamAbbrev: string;
    teamName: string;
    teamLogo: string;
    headshotUrl: string;
    heroImageUrl: string;
    height: string;
    weight: string;
    shootsCatches: string;
    birthDate: string;
    age: number | null;
    birthplace: string;
    draft: string;
    isActive: boolean;
    inHHOF: boolean;
  };
  headlineKpis: PlayerStatItem[];
  statGroups: PlayerStatGroup[];
  edge: PlayerEdgeData | null;
  gameLog: PlayerGameLogEntry[];
  careerTotals: {
    regularSeason: Record<string, number | string | null>;
    playoffs: Record<string, number | string | null>;
  };
  seasonTotals: PlayerSeasonRow[];
  awards: PlayerAward[];
  moneyPuck?: PlayerMoneyPuckData | null;
}

export type MoneyPuckSituationKey = "5on5" | "all" | "5on4" | "4on5";

export interface RadarAxisPoint {
  axis: string;
  percentile: number;
  display: string;
}

export interface DangerBarPoint {
  zone: string;
  shots: number;
  expected: number;
  actual: number;
}

export interface OnOffImpactRow {
  label: string;
  onIce: number;
  offIce: number;
  rel: number;
}

export interface ShiftStartSlice {
  label: string;
  count: number;
}

export interface ExpectedVsActualRow {
  label: string;
  expected: number;
  actual: number;
  delta: number;
  deltaLabel: string;
}

export interface PlayerMoneyPuckSituation {
  statGroups: PlayerStatGroup[];
  charts: {
    radar: RadarAxisPoint[];
    dangerBars: DangerBarPoint[];
    onOffImpact: OnOffImpactRow[];
    shiftStarts: ShiftStartSlice[];
    expectedVsActual: ExpectedVsActualRow[];
  };
}

export interface PlayerMoneyPuckData {
  source: string;
  defaultSituation: MoneyPuckSituationKey;
  situations: Partial<Record<MoneyPuckSituationKey, PlayerMoneyPuckSituation>>;
}
