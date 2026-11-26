import httpx
from analytics.models import TeamStanding

NHL_WEB_API_BASE = "https://api-web.nhle.com"


def fetch_and_store_standings(target_date: str | None = None) -> int:
    """
    Fetch NHL standings for 'now' or a specific YYYY-MM-DD date and upsert into DB.
    Returns the number of teams updated.
    """
    endpoint = f"/v1/standings/{target_date}" if target_date else "/v1/standings/now"

    with httpx.Client(
        base_url=NHL_WEB_API_BASE,
        follow_redirects=True,
        timeout=15.0,
    ) as client:
        response = client.get(endpoint)
        response.raise_for_status()
        payload = response.json()

    rows = payload.get("standings", [])
    updated_count = 0

    for item in rows:
        season_id = str(item.get("seasonId", ""))
        team_abbrev = item.get("teamAbbrev", {}).get("default", "")
        if not season_id or not team_abbrev:
            continue

        TeamStanding.objects.update_or_create(
            season_id=season_id,
            team_abbrev=team_abbrev,
            defaults={
                "team_name": item.get("teamName", {}).get("default", team_abbrev),
                "team_common_name": item.get("teamCommonName", {}).get(
                    "default", team_abbrev
                ),
                "team_logo": item.get("teamLogo", ""),
                "conference_name": item.get("conferenceName", ""),
                "division_name": item.get("divisionName", ""),
                "division_sequence": item.get("divisionSequence", 1),
                "games_played": item.get("gamesPlayed", 0),
                "wins": item.get("wins", 0),
                "losses": item.get("losses", 0),
                "ot_losses": item.get("otLosses", 0),
                "points": item.get("points", 0),
                "point_pctg": round(float(item.get("pointPctg", 0.0)), 3),
                "goals_for": item.get("goalFor", 0),
                "goals_against": item.get("goalAgainst", 0),
                "goal_differential": item.get("goalDifferential", 0),
                "l10_wins": item.get("l10Wins", 0),
                "l10_losses": item.get("l10Losses", 0),
                "l10_ot_losses": item.get("l10OtLosses", 0),
                "home_wins": item.get("homeWins", 0),
                "home_losses": item.get("homeLosses", 0),
                "home_ot_losses": item.get("homeOtLosses", 0),
                "road_wins": item.get("roadWins", 0),
                "road_losses": item.get("roadLosses", 0),
                "road_ot_losses": item.get("roadOtLosses", 0),
                "streak_code": item.get("streakCode", ""),
                "streak_count": item.get("streakCount", 0),
            },
        )
        updated_count += 1

    return updated_count
