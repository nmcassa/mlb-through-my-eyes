"""
espn_nfl.py
Thin wrapper around ESPN's public "hidden" API for the NFL. Same endpoint
family as espn_nba.py / espn_cbb.py (see the reference gist:
https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b), under
the "football/nfl" sport path.

Box scores here are split into three stat categories only — passing (QB),
rushing, and receiving — since that's all this tracker cares about.
Defense, kicking, punting, and return stats are intentionally not parsed.

A note on confidence: like the basketball wrappers, this shape is
reconstructed from community documentation of this endpoint, not a live
test in this environment (no network access to espn.com here). Football
box scores have more stat categories than basketball ones, and the exact
key ESPN uses to label each category (e.g. "passing" vs "Passing" vs some
other field) isn't confirmed — _category_of() below matches loosely
(substring match on "pass"/"rush"/"receiv") specifically to tolerate that
uncertainty. If something doesn't parse right (an empty stat category when
you know a game has one, weird numbers), run:

    python3 espn_nfl.py diagnose <game_id>

against a real completed game ID, same idea as espn_nba.py's diagnose().
"""
from __future__ import annotations

import sys

import nfl_dates

try:
    import requests
except ImportError:
    print("Error: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
_TIMEOUT = 15


def _get(path: str, **params) -> dict:
    url = f"{BASE}/{path}"
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"ESPN API request failed ({url}): {e}") from e


# ── Teams ──────────────────────────────────────────────────────────────────

def find_teams(query: str) -> list[dict]:
    """
    Look up NFL teams by name/city/abbreviation fragment (e.g. 'Eagles',
    'Philadelphia', 'PHI'). Returns a list of {"id", "name", "abbreviation"}.
    """
    data = _get("teams", limit=50)
    q = query.lower()
    out = []
    leagues = data.get("sports", [{}])[0].get("leagues", [{}])
    teams = leagues[0].get("teams", []) if leagues else []
    for entry in teams:
        t = entry.get("team", {})
        haystack = " ".join(str(t.get(k, "")) for k in
                             ("displayName", "shortDisplayName", "name", "location", "abbreviation")).lower()
        if q in haystack:
            out.append({
                "id": t.get("id"),
                "name": t.get("displayName", "?"),
                "abbreviation": t.get("abbreviation", "?"),
            })
    return out


# ── Schedule ───────────────────────────────────────────────────────────────

SEASON_TYPE_LABELS = {
    "1": "Preseason",
    "2": "Regular Season",
    "3": "Postseason (Playoffs + Super Bowl)",
}


def _score_value(competitor: dict) -> str:
    score = competitor.get("score", "")
    if isinstance(score, dict):
        return str(score.get("displayValue") or score.get("value") or "")
    return str(score) if score not in (None, "") else ""


def _parse_schedule_event(ev: dict) -> dict:
    comp = (ev.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    status = comp.get("status", {}).get("type", {})
    completed = bool(status.get("completed"))

    return {
        "game_id":    ev.get("id"),
        "game_date":  nfl_dates.espn_date_to_local(ev.get("date") or ""),
        "away_name":  away.get("team", {}).get("displayName", "?"),
        "home_name":  home.get("team", {}).get("displayName", "?"),
        "away_score": _score_value(away) if completed else "",
        "home_score": _score_value(home) if completed else "",
        "status":     status.get("shortDetail") or status.get("description") or "",
        "completed":  completed,
    }


def fetch_team_schedule(team_id: str, season: str, season_types: list[str] | None = None) -> list[dict]:
    """
    Fetch a team's game log for a season. season is the year the season
    STARTS in (e.g. '2024' for the 2024-25 season, matching how the NFL
    itself names seasons — no start/end-year conversion needed here, unlike
    the NBA tracker).

    season_types: '1' preseason, '2' regular season, '3' postseason.
    Defaults to ['2'] if omitted.

    Raises RuntimeError on API failure.
    """
    if season_types is None:
        season_types = ["2"]

    games = []
    seen_ids = set()
    for st in season_types:
        data = _get(f"teams/{team_id}/schedule", season=season, seasontype=st)
        for ev in data.get("events", []):
            gid = ev.get("id")
            if not gid or gid in seen_ids:
                continue
            seen_ids.add(gid)
            games.append(_parse_schedule_event(ev))
    games.sort(key=lambda g: g["game_date"])
    return games


def fetch_games_by_date(date: str, team_id: str | None = None) -> list[dict]:
    """
    Fetch all NFL games played on a single date (YYYY-MM-DD), optionally
    filtered to one team. Uses the scoreboard endpoint.

    Raises RuntimeError on API failure.
    """
    espn_date = date.replace("-", "")
    data = _get("scoreboard", dates=espn_date, limit=100)

    events = data.get("events", [])
    games  = [_parse_schedule_event(ev) for ev in events]

    if team_id is not None:
        team_id = str(team_id)
        events_by_id = {ev.get("id"): ev for ev in events}
        kept = []
        for g in games:
            ev = events_by_id.get(g["game_id"])
            ids = _event_team_ids(ev) if ev else {}
            if str(ids.get("away")) == team_id or str(ids.get("home")) == team_id:
                kept.append(g)
        games = kept

    games.sort(key=lambda g: g["game_date"])
    return games


def _event_team_ids(ev: dict) -> dict:
    comp = (ev.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    return {"away": away.get("team", {}).get("id"), "home": home.get("team", {}).get("id")}


# ── Boxscore ───────────────────────────────────────────────────────────────

_STAT_CATEGORIES = ("passing", "rushing", "receiving")

# ESPN's per-player box score column labels -> our canonical stat keys,
# one map per category (football box scores share far fewer column names
# across categories than basketball's single table did).
_LABEL_MAP_PASSING = {
    "C/ATT": "cmp_att", "YDS": "pass_yds", "AVG": "pass_avg", "TD": "pass_td",
    "INT": "int", "SACKS": "sacks", "QBR": "qbr", "RTG": "rtg",
}
_LABEL_MAP_RUSHING = {
    "CAR": "car", "YDS": "rush_yds", "AVG": "rush_avg", "TD": "rush_td", "LONG": "rush_long",
}
_LABEL_MAP_RECEIVING = {
    "REC": "rec", "YDS": "rec_yds", "AVG": "rec_avg", "TD": "rec_td",
    "LONG": "rec_long", "TGTS": "tgts",
}


def _category_of(stat_group: dict) -> str | None:
    """Loosely match a box score stat-group to one of our three tracked
    categories, tolerant of exactly which JSON key/casing ESPN uses (see
    the module confidence note above)."""
    name = str(stat_group.get("name") or stat_group.get("displayName")
               or stat_group.get("text") or stat_group.get("type") or "").lower()
    if "pass" in name:
        return "passing"
    if "rush" in name:
        return "rushing"
    if "receiv" in name:
        return "receiving"
    return None


def _split_on(sep: str, s) -> tuple[int, int]:
    """Parse a 'X{sep}Y' cell like '24/35' or '3-24' -> (24, 35)."""
    try:
        a, b = str(s).split(sep)
        return int(a), int(b)
    except (ValueError, AttributeError):
        return 0, 0


def _to_int(s) -> int:
    """Parse an int, stripping a trailing 'T' (touchdown-flagged long gain, e.g. '42T')."""
    try:
        return int(str(s).strip().rstrip("T"))
    except (ValueError, TypeError):
        return 0


def _to_float(s) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _parse_passing_row(labels: list[str], raw_stats: list) -> dict:
    row = dict(zip([_LABEL_MAP_PASSING.get(l, str(l).lower()) for l in labels], raw_stats))
    cmp_, att = _split_on("/", row.get("cmp_att", "0/0"))
    sacks, sack_yds = _split_on("-", row.get("sacks", "0-0"))
    return {
        "cmp": cmp_, "att": att,
        "pass_yds": _to_int(row.get("pass_yds", 0)),
        "pass_td":  _to_int(row.get("pass_td", 0)),
        "int":      _to_int(row.get("int", 0)),
        "sacks":    sacks, "sack_yds": sack_yds,
        "qbr":      _to_float(row.get("qbr", 0)),
        "rtg":      _to_float(row.get("rtg", 0)),
    }


def _parse_rushing_row(labels: list[str], raw_stats: list) -> dict:
    row = dict(zip([_LABEL_MAP_RUSHING.get(l, str(l).lower()) for l in labels], raw_stats))
    return {
        "car":       _to_int(row.get("car", 0)),
        "rush_yds":  _to_int(row.get("rush_yds", 0)),
        "rush_td":   _to_int(row.get("rush_td", 0)),
        "rush_long": _to_int(row.get("rush_long", 0)),
    }


def _parse_receiving_row(labels: list[str], raw_stats: list) -> dict:
    row = dict(zip([_LABEL_MAP_RECEIVING.get(l, str(l).lower()) for l in labels], raw_stats))
    return {
        "rec":      _to_int(row.get("rec", 0)),
        "rec_yds":  _to_int(row.get("rec_yds", 0)),
        "rec_td":   _to_int(row.get("rec_td", 0)),
        "rec_long": _to_int(row.get("rec_long", 0)),
        "tgts":     _to_int(row.get("tgts", 0)),
    }


_PARSERS = {
    "passing": _parse_passing_row,
    "rushing": _parse_rushing_row,
    "receiving": _parse_receiving_row,
}


def fetch_boxscore_data(game_id: str) -> dict:
    """
    Return per-player box score stats for one game, keyed by side and then
    by stat category:
      {"away": {"team": name,
                "passing":   {athlete_id: {"name":..., "stats": {...}}},
                "rushing":   {athlete_id: {...}},
                "receiving": {athlete_id: {...}}},
       "home": {...}}
    Raises RuntimeError on failure or if ESPN hasn't posted a box score yet.
    """
    data = _get("summary", event=game_id)
    box = data.get("boxscore", {})
    player_blocks = box.get("players", [])
    if not player_blocks:
        raise RuntimeError("No box score available for this game yet (ESPN may still be finalizing it).")

    header_competitors = ((data.get("header", {}).get("competitions") or [{}])[0]
                           .get("competitors", []))
    home_away_by_team_id = {c.get("team", {}).get("id"): c.get("homeAway") for c in header_competitors}

    result = {
        "away": {"team": "?", "passing": {}, "rushing": {}, "receiving": {}},
        "home": {"team": "?", "passing": {}, "rushing": {}, "receiving": {}},
    }

    for block in player_blocks:
        team_info = block.get("team", {})
        team_id   = team_info.get("id")
        side      = home_away_by_team_id.get(team_id, "away")
        if side not in ("home", "away"):
            side = "away"
        result[side]["team"] = team_info.get("displayName", "?")

        for stat_group in block.get("statistics", []):
            category = _category_of(stat_group)
            if category is None:
                continue   # defense/kicking/punting/returns — not tracked here
            labels = stat_group.get("labels") or stat_group.get("names") or []
            parser = _PARSERS[category]
            for athlete_row in stat_group.get("athletes", []):
                athlete = athlete_row.get("athlete", {})
                athlete_id = athlete.get("id")
                raw_stats  = athlete_row.get("stats", [])
                if not athlete_id or not raw_stats or len(raw_stats) != len(labels):
                    continue   # DNP or a row shape we don't recognize — skip it
                result[side][category][athlete_id] = {
                    "name": athlete.get("displayName", str(athlete_id)),
                    "stats": parser(labels, raw_stats),
                }

    return result


# ── Dev helper ─────────────────────────────────────────────────────────────

def diagnose(game_id: str):
    """
    Dump the raw JSON shape ESPN actually returns for one game, so parsing
    above can be fixed up if it doesn't match reality. Run directly:
    `python3 espn_nfl.py diagnose <game_id>`
    """
    import json
    data = _get("summary", event=game_id)
    box = data.get("boxscore", {})
    print("Top-level boxscore keys:", list(box.keys()))
    players = box.get("players", [])
    if players:
        print("\nFirst team block keys:", list(players[0].keys()))
        stats = players[0].get("statistics", [])
        for sg in stats:
            print(f"\n--- stat group: name={sg.get('name')!r} displayName={sg.get('displayName')!r} ---")
            print("Labels:", sg.get("labels") or sg.get("names"))
            athletes = sg.get("athletes", [])
            if athletes:
                print("First athlete row (raw):")
                print(json.dumps(athletes[0], indent=2))
    else:
        print("No 'players' block found — dumping full boxscore JSON (truncated):")
        print(json.dumps(box, indent=2)[:3000])


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "diagnose":
        diagnose(sys.argv[2])
    else:
        print("Usage: python3 espn_nfl.py diagnose <game_id>")
