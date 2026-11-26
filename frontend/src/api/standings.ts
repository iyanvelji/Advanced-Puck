import type { StandingsResponse } from "../types/standings";

export async function fetchStandings(season = ""): Promise<StandingsResponse> {
  const query = season ? `?season=${encodeURIComponent(season)}` : "";
  const response = await fetch(`/api/standings${query}`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load standings (${response.status})`);
  }

  return (await response.json()) as StandingsResponse;
}
