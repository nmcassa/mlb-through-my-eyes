"""
mlb.py
Thin wrappers around the MLB-StatsAPI library.
All calls to statsapi live here — nothing else in the project imports statsapi directly.
"""
from __future__ import annotations

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


# Human-readable labels for MLB game type codes
GAME_TYPE_LABELS = {
    "S": "Spring Training",
    "R": "Regular Season",
    "F": "Wild Card",
    "D": "Division Series (ALDS/NLDS)",
    "L": "League Championship (ALCS/NLCS)",
    "W": "World Series",
}


def fetch_season_schedule(
    team_id: int,
    season: str,
    game_types: list[str] | None = None,
) -> list[dict]:
    """
    Fetch games for a team in a given year, filtered to the requested game types.
    game_types: list of type codes e.g. ['R', 'F', 'D', 'L', 'W'].
                Defaults to ['R'] (regular season only).
    Raises RuntimeError on API failure.
    """
    if game_types is None:
        game_types = ["R"]

    try:
        schedule = statsapi.schedule(
            team=team_id,
            start_date=f"{season}-01-01",
            end_date=f"{season}-12-31",
            sportId=1,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch schedule: {e}") from e

    return [g for g in schedule if g.get("game_type") in game_types]


def fetch_boxscore(game_id: int) -> str:
    """Return a formatted boxscore string for a single game."""
    return statsapi.boxscore(game_id)


def fetch_boxscore_data(game_id: int) -> dict:
    """
    Return the raw boxscore data dict for a single game.
    Contains per-player batting and pitching stats under:
      result['away']['players']  and  result['home']['players']
    Each player entry has:
      p['seasonStats']['batting']  — avg, ops, obp, slg, ...
      p['seasonStats']['pitching'] — era, inningsPitched, earnedRuns, ...
      p['stats']['batting']        — game-level batting stats
      p['stats']['pitching']       — game-level pitching stats (ip, h, r, er, bb, k, hr)
    Raises RuntimeError on failure.
    """
    try:
        return statsapi.boxscore_data(game_id)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch boxscore data for game {game_id}: {e}") from e


def fetch_player_stat_data(person_id: int, group: str, stat_type: str, season: str | None = None) -> dict:
    """
    Return raw stat data for a single player.
      group:     'hitting' or 'pitching'
      stat_type: 'career' or 'season'
      season:    e.g. '2014' — required when stat_type='season'

    Returns the dict from statsapi.player_stat_data(), which has:
      result['stats'][0]['splits'][0]['stat']  — the stat dict
    Raises RuntimeError on failure or if no data found.
    """
    try:
        kwargs = dict(group=group, type=stat_type, sportId=1)
        if season:
            kwargs["season"] = season
        data = statsapi.player_stat_data(person_id, **kwargs)
        return data
    except Exception as e:
        raise RuntimeError(f"Failed to fetch stats for player {person_id}: {e}") from e


def lookup_player_id(full_name: str) -> int | None:
    """
    Look up a player's MLB person ID by full name.
    Returns the first match's ID, or None if not found.
    """
    results = statsapi.lookup_player(full_name)
    if results:
        return results[0]["id"]
    return None
