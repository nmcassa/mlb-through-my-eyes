"""
espn_nba.py
Thin wrapper around ESPN's public "hidden" API for NBA data.
All HTTP calls live here — nothing else in this project talks to ESPN directly.

Reference: https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b

A note on confidence: ESPN doesn't publish an official spec for this API. The
JSON shape assumed below (boxscore.players[].statistics[].athletes[].stats)
is reconstructed from widely-shared community documentation of this same
endpoint, not from a live test — this environment has no network access to
espn.com to verify against. If something doesn't parse right (an empty
Player Summary when you know a game has a box score, weird numbers, etc.),
run:

    python3 espn_nba.py diagnose <game_id>

against a real completed game ID from your watched list. It dumps the raw
JSON shape ESPN actually sent, which is exactly what's needed to fix the
parsing in _parse_athlete_row() / fetch_boxscore_data() below.
"""
from __future__ import annotations

import sys

import nba_dates

try:
    import requests
except ImportError:
    print("Error: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
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
    Look up NBA teams by name/city/abbreviation fragment (e.g. 'Celtics',
    'Boston', 'BOS'). Returns a list of {"id", "name", "abbreviation"}.
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
    "3": "Postseason (playoffs + play-in)",
}

# ESPN doesn't publish a stable "seasontype" code for the Play-In
# Tournament — in some seasons it seems to be folded into type 3
# (postseason), in others it may need a different code. Rather than risk
# silently dropping play-in games by guessing wrong, whenever postseason is
# requested we also probe a couple of extra candidate codes and merge in
# anything new. A code that doesn't exist for this team/season just comes
# back with zero events, which is harmless — just an extra request or two.
_PLAY_IN_PROBE_CODES = ["4", "5"]


def _score_value(competitor: dict) -> str:
    """
    Normalize ESPN's score field to a plain string. In practice this comes
    back as a dict like {"value": 112.0, "displayValue": "112"} rather than
    a bare string/number — bug fix for a crash + garbled display that
    happened when this was assumed to already be a string.
    """
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
        "game_date":  nba_dates.espn_date_to_local(ev.get("date") or ""),
        "away_name":  away.get("team", {}).get("displayName", "?"),
        "home_name":  home.get("team", {}).get("displayName", "?"),
        "away_score": _score_value(away) if completed else "",
        "home_score": _score_value(home) if completed else "",
        "status":     status.get("shortDetail") or status.get("description") or "",
        "completed":  completed,
    }


def fetch_team_schedule(team_id: str, season: str, season_types: list[str] | None = None) -> list[dict]:
    """
    Fetch a team's game log for a season. Returns a list of dicts:
      {game_id, game_date, away_name, home_name, away_score, home_score,
       status, completed}

    season_types: ESPN "seasontype" codes to include — '1' preseason,
    '2' regular season, '3' postseason. Defaults to ['2'] (regular season
    only) if omitted. The schedule endpoint only returns one season type
    per request, so postseason games are invisible unless requested
    explicitly. If '3' is included, a couple of extra candidate codes are
    also probed to catch play-in games (see _PLAY_IN_PROBE_CODES above).

    Raises RuntimeError on API failure.
    """
    if season_types is None:
        season_types = ["2"]

    codes_to_try = list(season_types)
    if "3" in codes_to_try:
        codes_to_try += [c for c in _PLAY_IN_PROBE_CODES if c not in codes_to_try]

    games = []
    seen_ids = set()
    for st in codes_to_try:
        try:
            data = _get(f"teams/{team_id}/schedule", season=season, seasontype=st)
        except RuntimeError:
            if st in season_types:
                raise   # a code the user actually asked for should still error loudly
            continue    # a probe code failing is fine — it may just not exist
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
    Fetch all games played on a single date (YYYY-MM-DD), optionally
    filtered to one team. Uses ESPN's "scoreboard" endpoint, which is keyed
    by date rather than by team — a separate endpoint from the
    teams/{id}/schedule one fetch_team_schedule() uses, so this doesn't
    disturb that path at all.

    Note: the scoreboard endpoint wants dates as YYYYMMDD (no dashes),
    unlike everywhere else in this file that uses YYYY-MM-DD — that
    conversion happens here so callers keep using the normal format.

    Raises RuntimeError on API failure.
    """
    espn_date = date.replace("-", "")
    data = _get("scoreboard", dates=espn_date, limit=100)

    games = [_parse_schedule_event(ev) for ev in data.get("events", [])]

    if team_id is not None:
        team_id = str(team_id)
        events_by_id = {ev.get("id"): ev for ev in data.get("events", [])}
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
    """Map home/away -> team id for one scoreboard event, for team filtering."""
    comp = (ev.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    return {"away": away.get("team", {}).get("id"), "home": home.get("team", {}).get("id")}


# ── Boxscore ───────────────────────────────────────────────────────────────

# ESPN's per-player box score column labels -> our canonical stat keys.
_LABEL_MAP = {
    "MIN": "min", "FG": "fg", "3PT": "3pt", "FT": "ft",
    "OREB": "oreb", "DREB": "dreb", "REB": "reb", "AST": "ast",
    "STL": "stl", "BLK": "blk", "TO": "tov", "PF": "pf",
    "+/-": "plusminus", "PTS": "pts",
}


def _split_made_attempted(s) -> tuple[int, int]:
    """Parse a 'made-attempted' box score cell like '10-15' -> (10, 15)."""
    try:
        made, att = str(s).split("-")
        return int(made), int(att)
    except (ValueError, AttributeError):
        return 0, 0


def _to_int(s) -> int:
    try:
        return int(str(s).strip())
    except (ValueError, TypeError):
        return 0


def _parse_athlete_row(labels: list[str], raw_stats: list) -> dict:
    """Turn one athlete's ['36','10-15','3-5',...] row into a stat dict."""
    row = dict(zip([_LABEL_MAP.get(l, str(l).lower()) for l in labels], raw_stats))

    fgm, fga = _split_made_attempted(row.get("fg", "0-0"))
    tpm, tpa = _split_made_attempted(row.get("3pt", "0-0"))
    ftm, fta = _split_made_attempted(row.get("ft", "0-0"))

    try:
        minutes = float(row.get("min", 0) or 0)
    except (ValueError, TypeError):
        minutes = 0.0

    return {
        "min":  minutes,
        "fgm": fgm, "fga": fga,
        "3pm": tpm, "3pa": tpa,
        "ftm": ftm, "fta": fta,
        "oreb": _to_int(row.get("oreb", 0)),
        "dreb": _to_int(row.get("dreb", 0)),
        "reb":  _to_int(row.get("reb", 0)),
        "ast":  _to_int(row.get("ast", 0)),
        "stl":  _to_int(row.get("stl", 0)),
        "blk":  _to_int(row.get("blk", 0)),
        "tov":  _to_int(row.get("tov", 0)),
        "pf":   _to_int(row.get("pf", 0)),
        "pts":  _to_int(row.get("pts", 0)),
    }


def fetch_boxscore_data(game_id: str) -> dict:
    """
    Return per-player box score stats for one game, keyed by side:
      {"away": {"team": name, "players": {athlete_id: {"name":..., "stats": {...}}}},
       "home": {...}}
    Raises RuntimeError on failure or if ESPN hasn't posted a box score yet
    (this can lag behind the final score for a bit after a game ends).
    """
    data = _get("summary", event=game_id)
    box = data.get("boxscore", {})
    player_blocks = box.get("players", [])
    if not player_blocks:
        raise RuntimeError("No box score available for this game yet (ESPN may still be finalizing it).")

    # Map team id -> home/away using the header's competitors, so sides line
    # up with how the schedule/watched-game data labels them.
    header_competitors = ((data.get("header", {}).get("competitions") or [{}])[0]
                           .get("competitors", []))
    home_away_by_team_id = {c.get("team", {}).get("id"): c.get("homeAway") for c in header_competitors}

    result = {"away": {"team": "?", "players": {}}, "home": {"team": "?", "players": {}}}

    for block in player_blocks:
        team_info = block.get("team", {})
        team_id   = team_info.get("id")
        side      = home_away_by_team_id.get(team_id, "away")
        if side not in ("home", "away"):
            side = "away"
        result[side]["team"] = team_info.get("displayName", "?")

        for stat_group in block.get("statistics", []):
            labels = stat_group.get("labels") or stat_group.get("names") or []
            for athlete_row in stat_group.get("athletes", []):
                athlete = athlete_row.get("athlete", {})
                athlete_id = athlete.get("id")
                raw_stats  = athlete_row.get("stats", [])
                if not athlete_id or not raw_stats or len(raw_stats) != len(labels):
                    continue   # DNP or a row shape we don't recognize — skip it
                result[side]["players"][athlete_id] = {
                    "name": athlete.get("displayName", str(athlete_id)),
                    "stats": _parse_athlete_row(labels, raw_stats),
                }

    return result


# ── Dev helper ─────────────────────────────────────────────────────────────

def diagnose(game_id: str):
    """
    Dump the raw JSON shape ESPN actually returns for one game, so parsing
    above can be fixed up if it doesn't match reality. Not used by the
    normal app — run directly: `python3 espn_nba.py diagnose <game_id>`
    """
    import json
    data = _get("summary", event=game_id)
    box = data.get("boxscore", {})
    print("Top-level boxscore keys:", list(box.keys()))
    players = box.get("players", [])
    if players:
        print("\nFirst team block keys:", list(players[0].keys()))
        stats = players[0].get("statistics", [])
        if stats:
            print("First statistics group keys:", list(stats[0].keys()))
            print("Labels:", stats[0].get("labels") or stats[0].get("names"))
            athletes = stats[0].get("athletes", [])
            if athletes:
                print("\nFirst athlete row (raw):")
                print(json.dumps(athletes[0], indent=2))
    else:
        print("No 'players' block found — dumping full boxscore JSON (truncated):")
        print(json.dumps(box, indent=2)[:3000])


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "diagnose":
        diagnose(sys.argv[2])
    else:
        print("Usage: python3 espn_nba.py diagnose <game_id>")
