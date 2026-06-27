"""
mlb.py
Thin wrappers around the MLB-StatsAPI library.
All calls to statsapi live here — nothing else in the project imports statsapi directly.
"""

import sys

try:
    import statsapi
except ImportError:
    print("Error: MLB-StatsAPI not installed. Run: pip install MLB-StatsAPI")
    sys.exit(1)


def find_teams(query: str) -> list[dict]:
    """
    Look up teams by name fragment (e.g. 'Braves', 'New York').
    Returns a list of dicts with at least 'id' and 'name'.
    """
    return statsapi.lookup_team(query)


def fetch_season_schedule(team_id: int, season: str) -> list[dict]:
    """
    Fetch all regular-season games for a team in a given year.
    Returns a list of game dicts from statsapi.schedule(), filtered to game_type == 'R'.
    Raises RuntimeError on API failure.
    """
    try:
        schedule = statsapi.schedule(
            team=team_id,
            start_date=f"{season}-01-01",
            end_date=f"{season}-12-31",
            sportId=1,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch schedule: {e}") from e

    return [g for g in schedule if g.get("game_type") == "R"]


def fetch_boxscore(game_id: int) -> str:
    """Return a formatted boxscore string for a single game."""
    return statsapi.boxscore(game_id)
