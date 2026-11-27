import type { StandingsResponse } from "../types/standings";
import { API_BASE } from "./config";

export async function fetchStandings(season = ""): Promise<StandingsResponse> {
  const query = season ? `?season=${encodeURIComponent(season)}` : "";
  const response = await fetch(`${API_BASE}/api/standings${query}`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load standings (${response.status})`);
  }

  return (await response.json()) as StandingsResponse;
}
