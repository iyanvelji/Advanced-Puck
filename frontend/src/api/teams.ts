import type { TeamProfileResponse } from "../types/teams";

export async function fetchTeamProfile(
  teamAbbrev: string,
): Promise<TeamProfileResponse> {
  const response = await fetch(`/api/teams/${encodeURIComponent(teamAbbrev)}`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(
      `Failed to load ${teamAbbrev} profile (${response.status})`,
    );
  }

  return (await response.json()) as TeamProfileResponse;
}
