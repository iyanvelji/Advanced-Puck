import type {
  PlayerCategoryKey,
  PlayerCategoryResponse,
  PlayerProfileResponse,
  PlayerSearchResponse,
  PlayersLeadersResponse,
} from "../types/players";

export async function fetchPlayerLeaders(): Promise<PlayersLeadersResponse> {
  const response = await fetch("/api/players/leaders", {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load player leaders (${response.status})`);
  }
  return response.json() as Promise<PlayersLeadersResponse>;
}

export async function fetchPlayerCategory(
  category: PlayerCategoryKey,
  qualifiedOnly = true,
): Promise<PlayerCategoryResponse> {
  const query =
    category === "goalies" ? `?qualified_only=${qualifiedOnly}` : "";
  const response = await fetch(`/api/players/category/${category}${query}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load ${category} list (${response.status})`);
  }
  return response.json() as Promise<PlayerCategoryResponse>;
}

export async function searchPlayers(q: string): Promise<PlayerSearchResponse> {
  const response = await fetch(
    `/api/players/search?q=${encodeURIComponent(q)}`,
    { credentials: "include" },
  );
  if (!response.ok) {
    throw new Error(`Search failed (${response.status})`);
  }
  return response.json() as Promise<PlayerSearchResponse>;
}

export async function fetchPlayerProfile(
  playerId: number,
): Promise<PlayerProfileResponse> {
  const response = await fetch(`/api/players/${playerId}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load player profile (${response.status})`);
  }
  return response.json() as Promise<PlayerProfileResponse>;
}
