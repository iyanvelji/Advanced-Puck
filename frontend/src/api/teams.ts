import type { TeamProfileResponse } from "../types/teams";
import { API_BASE } from "./config";

export async function fetchTeamProfile(
  teamAbbrev: string,
): Promise<TeamProfileResponse> {
  const response = await fetch(
    `${API_BASE}/api/teams/${encodeURIComponent(teamAbbrev)}`,
    {
      credentials: "include",
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to load ${teamAbbrev} profile (${response.status})`,
    );
  }

  return (await response.json()) as TeamProfileResponse;
}
