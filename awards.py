#!/usr/bin/env python3
"""
awards.py
Fan Awards report — scans for watched-games JSON files from ANY sport
tracker in this project (MLB, NBA, or a future one) and hands out trophies
based on how much of each team's real season you actually watched.

Deliberately lives outside any single sport's files: it doesn't hardcode
MLB or NBA internals directly. Instead each sport plugs in through a small
adapter in LEAGUES below (season_of / find_team_id / team_games). Sport
detection for a given JSON file is by filename hint (falls back to MLB's
shape, since that was the first tracker), not by import structure, so this
still works if you reorganize the trackers into subfolders later — just
point it at the right root: `python3 awards.py path/to/data`.

Requires mlb.py (for MLB files) and/or espn_nba.py + nba_dates.py (for NBA
files) to be importable, since verifying "how much of the season" needs a
real schedule to compare against — but a file is only skipped (with a
message), not fatal, if its sport's adapter isn't available.

Trophies:
  Season Attendance  — Gold (100%) / Silver (75%+) / Bronze (50%+) of a
                        team's REGULAR season games, per team per season.
  Playoff Perfect     — watched every playoff game a team played that season
                        (only awarded if the team actually made the playoffs).
  Iron Fan            — watched literally every game (regular + playoff
                         combined) for a team's season.
  Wire to Wire        — watched that team's regular-season opener AND finale.
  Century Club        — 100+ total games logged across everything.
  Multi-Sport Fan     — has logged games in more than one sport.

Usage:
    python3 awards.py                  # scan current directory (recursive)
    python3 awards.py /path/to/data    # scan a specific directory instead
"""
from __future__ import annotations

import glob
import importlib
import json
import os
import sys
from collections import defaultdict

# mlb.py / espn_nba.py / nba_dates.py aren't assumed to live next to this
# file — your project may keep them under sport-specific folders (e.g.
# ./src/mlb.py, ./nba/espn_nba.py). These are located and imported
# dynamically in build_leagues() below, once we know the scan root.
mlb = None
espn_nba = None
nba_dates = None


PLAYOFF_TYPES_MLB = {"F", "D", "L", "W"}   # wild card / division / league / WS
_team_id_cache: dict[tuple[str, str], object] = {}


# ── Dynamic module discovery ─────────────────────────────────────────────────
# Sport support modules can live anywhere under the scan root (e.g.
# ./src/mlb.py, ./nba/espn_nba.py + ./nba/nba_dates.py). We search for them
# rather than assuming a fixed layout, and add whichever directory each one
# is found in to sys.path so its own sibling imports (like espn_nba's
# `import nba_dates`) still resolve normally.

def _find_module_file(root: str, module_name: str) -> str | None:
    matches = glob.glob(os.path.join(root, "**", f"{module_name}.py"), recursive=True)
    return matches[0] if matches else None


def _import_from_root(module_name: str, root: str):
    """Locate {module_name}.py anywhere under root and import it. Returns
    None (rather than raising) if it can't be found or fails to import —
    e.g. because its own dependency (like MLB-StatsAPI) isn't installed."""
    path = _find_module_file(root, module_name)
    if not path:
        return None
    directory = os.path.dirname(os.path.abspath(path))
    if directory not in sys.path:
        sys.path.insert(0, directory)
    try:
        return importlib.import_module(module_name)
    except (ImportError, SystemExit):
        return None


# ── Discovery ────────────────────────────────────────────────────────────────

def discover_watched_files(root: str = ".") -> list[dict]:
    """
    Find watched-games JSON files under `root` (recursive) and guess which
    sport each belongs to. A file qualifies if it's a non-empty JSON object
    whose values look like watched-game records (have game_id/date/away/home).
    Returns a list of {"path", "sport", "data"}.
    """
    found = []
    for path in sorted(glob.glob(os.path.join(root, "**", "*.json"), recursive=True)):
        base = os.path.basename(path)
        if base.endswith(".bak"):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or not data:
            continue

        sample = next(iter(data.values()))
        if not isinstance(sample, dict):
            continue
        if not {"game_id", "date", "away", "home"}.issubset(sample.keys()):
            continue   # doesn't look like a watched-games record

        sport = "nba" if "nba" in base.lower() else "mlb"
        found.append({"path": path, "sport": sport, "data": data})
    return found


# ── MLB adapter ────────────────────────────────────────────────────────────

def _mlb_find_team_id(name: str):
    key = ("mlb", name)
    if key in _team_id_cache:
        return _team_id_cache[key]
    tid = None
    try:
        results = mlb.find_teams(name)
    except Exception:
        results = []
    for t in results:
        if t.get("name") == name:
            tid = t["id"]
            break
    if tid is None and results:
        tid = results[0]["id"]
    _team_id_cache[key] = tid
    return tid


def _mlb_team_games(team_id, season: str) -> dict:
    """gid(str) -> {'kind': 'regular'|'playoff', 'date': 'YYYY-MM-DD'} for one team's season."""
    types_to_fetch = ["R"] + sorted(PLAYOFF_TYPES_MLB)
    games = mlb.fetch_season_schedule(team_id, season, game_types=types_to_fetch)
    out = {}
    for g in games:
        gid = str(g.get("game_id"))
        kind = "regular" if g.get("game_type") == "R" else "playoff"
        out[gid] = {"kind": kind, "date": g.get("game_date", "")}
    return out


# ── NBA adapter ────────────────────────────────────────────────────────────

def _nba_find_team_id(name: str):
    key = ("nba", name)
    if key in _team_id_cache:
        return _team_id_cache[key]
    tid = None
    try:
        results = espn_nba.find_teams(name)
    except Exception:
        results = []
    for t in results:
        if t.get("name") == name:
            tid = t["id"]
            break
    if tid is None and results:
        tid = results[0]["id"]
    _team_id_cache[key] = tid
    return tid


def _nba_season_param(season_label: str) -> str:
    """'2023-24' -> '2024' — fetch_team_schedule wants the year the season ENDS in."""
    start = season_label.split("-")[0]
    return str(int(start) + 1)


def _nba_team_games(team_id, season_label: str) -> dict:
    """gid(str) -> {'kind': 'regular'|'playoff', 'date': 'YYYY-MM-DD'} for one team's season."""
    param = _nba_season_param(season_label)
    reg  = espn_nba.fetch_team_schedule(team_id, param, season_types=["2"])
    post = espn_nba.fetch_team_schedule(team_id, param, season_types=["3"])
    out = {}
    for g in reg:
        out[str(g["game_id"])] = {"kind": "regular", "date": g.get("game_date", "")}
    for g in post:
        out[str(g["game_id"])] = {"kind": "playoff", "date": g.get("game_date", "")}
    return out


def build_leagues(root: str) -> dict:
    """Locate and import each sport's support module(s) from under `root`,
    then build the adapter table. Call once per run, before compute_awards."""
    global mlb, espn_nba, nba_dates
    mlb       = _import_from_root("mlb", root)
    espn_nba  = _import_from_root("espn_nba", root)
    nba_dates = _import_from_root("nba_dates", root)

    return {
        "mlb": {
            "available":    mlb is not None,
            "icon":         "⚾",
            "season_of":    (lambda date: date.split("-")[0]) if mlb else None,
            "find_team_id": _mlb_find_team_id if mlb else None,
            "team_games":   _mlb_team_games if mlb else None,
        },
        "nba": {
            "available":    espn_nba is not None and nba_dates is not None,
            "icon":         "🏀",
            "season_of":    nba_dates.season_label if nba_dates else None,
            "find_team_id": _nba_find_team_id if espn_nba else None,
            "team_games":   _nba_team_games if espn_nba else None,
        },
    }


# ── Computation ────────────────────────────────────────────────────────────

def compute_awards(files: list[dict], leagues: dict) -> dict:
    """Cross-check every team/season a person has watched games for against
    the real schedule, and return the awards they qualify for."""
    buckets: dict[tuple[str, str, str], set] = defaultdict(set)  # (sport,team,season) -> watched gids
    total_watched = 0
    sports_seen: set[str] = set()

    for entry in files:
        sport  = entry["sport"]
        league = leagues.get(sport)
        if not league or not league["available"]:
            print(f"  Skipping {entry['path']} — no adapter available for '{sport}'.")
            continue
        sports_seen.add(sport)
        for g in entry["data"].values():
            total_watched += 1
            try:
                season = league["season_of"](g["date"])
            except Exception:
                continue
            for team_name in (g.get("away"), g.get("home")):
                if team_name:
                    buckets[(sport, team_name, season)].add(str(g.get("game_id")))

    trophies, playoff_perfect, iron_fan, wire_to_wire = [], [], [], []

    print(f"\nChecking {len(buckets)} team/season combination(s) against real schedules...\n")
    for (sport, team_name, season), watched_ids in sorted(buckets.items()):
        league  = leagues[sport]
        team_id = league["find_team_id"](team_name)
        if team_id is None:
            print(f"  {league['icon']} {team_name} — couldn't resolve team ID, skipping.")
            continue

        print(f"  {league['icon']} {team_name} — {season}...")
        try:
            game_map = league["team_games"](team_id, season)
        except RuntimeError as e:
            print(f"      Could not verify schedule: {e}")
            continue
        if not game_map:
            continue

        regular = {gid: v for gid, v in game_map.items() if v["kind"] == "regular"}
        playoff = {gid: v for gid, v in game_map.items() if v["kind"] == "playoff"}
        regular_ids, playoff_ids = set(regular), set(playoff)

        watched_regular = watched_ids & regular_ids
        watched_playoff = watched_ids & playoff_ids

        # Season attendance trophy (regular season only)
        if regular_ids:
            pct = len(watched_regular) / len(regular_ids)
            tier = "gold" if pct >= 1.0 else "silver" if pct >= 0.75 else "bronze" if pct >= 0.5 else None
            if tier:
                trophies.append({
                    "sport": sport, "team": team_name, "season": season, "tier": tier,
                    "watched": len(watched_regular), "total": len(regular_ids), "pct": pct,
                })

        # Playoff Perfect Attendance — only if the team actually made the playoffs
        if playoff_ids and watched_playoff == playoff_ids:
            playoff_perfect.append({
                "sport": sport, "team": team_name, "season": season, "games": len(playoff_ids),
            })

        # Iron Fan — every game, regular + playoff combined
        all_ids = regular_ids | playoff_ids
        if all_ids and (watched_regular | watched_playoff) == all_ids:
            iron_fan.append({"sport": sport, "team": team_name, "season": season, "games": len(all_ids)})

        # Wire to Wire — watched the regular-season opener AND the finale
        if regular:
            ordered = sorted(regular.items(), key=lambda kv: kv[1]["date"])
            first_gid, last_gid = ordered[0][0], ordered[-1][0]
            if first_gid in watched_regular and last_gid in watched_regular and first_gid != last_gid:
                wire_to_wire.append({"sport": sport, "team": team_name, "season": season})

    return {
        "trophies": trophies,
        "playoff_perfect": playoff_perfect,
        "iron_fan": iron_fan,
        "wire_to_wire": wire_to_wire,
        "total_watched": total_watched,
        "sports_seen": sports_seen,
    }


# ── Report ─────────────────────────────────────────────────────────────────

_TIER_ICON  = {"gold": "🥇", "silver": "🥈", "bronze": "🥉"}
_TIER_LABEL = {"gold": "Gold — 100%", "silver": "Silver — 75%+", "bronze": "Bronze — 50%+"}
_TIER_RANK  = {"gold": 3, "silver": 2, "bronze": 1}
_SPORT_ICON = {"mlb": "⚾", "nba": "🏀"}


def print_report(results: dict):
    print("\n" + "=" * 62)
    print("  🏆  FAN AWARDS")
    print("=" * 62)

    trophies = results["trophies"]
    if trophies:
        print("\n  Season Attendance Trophies\n")
        for t in sorted(trophies, key=lambda t: (-_TIER_RANK[t["tier"]], t["team"], t["season"])):
            icon = _SPORT_ICON.get(t["sport"], "")
            print(f"    {_TIER_ICON[t['tier']]} {icon} {t['team']} — {t['season']}   "
                  f"{t['watched']}/{t['total']} games ({t['pct']*100:.0f}%)   [{_TIER_LABEL[t['tier']]}]")
    else:
        print("\n  No season attendance trophies yet — watch at least half a team's")
        print("  regular season to earn bronze.")

    if results["playoff_perfect"]:
        print("\n  🏆 Playoff Perfect Attendance\n")
        for p in results["playoff_perfect"]:
            icon = _SPORT_ICON.get(p["sport"], "")
            print(f"    {icon} {p['team']} — {p['season']}   ({p['games']}/{p['games']} playoff games)")

    if results["iron_fan"]:
        print("\n  🔩 Iron Fan — every game, start to finish\n")
        for i in results["iron_fan"]:
            icon = _SPORT_ICON.get(i["sport"], "")
            print(f"    {icon} {i['team']} — {i['season']}   ({i['games']}/{i['games']} games)")

    if results["wire_to_wire"]:
        print("\n  🎬 Wire to Wire — watched opening day AND the season finale\n")
        for w in results["wire_to_wire"]:
            icon = _SPORT_ICON.get(w["sport"], "")
            print(f"    {icon} {w['team']} — {w['season']}")

    print("\n  Milestones\n")
    print(f"    🎟️  Total games logged: {results['total_watched']}")
    if results["total_watched"] >= 100:
        print(f"    💯 Century Club — 100+ games logged!")
    if len(results["sports_seen"]) > 1:
        leagues = ", ".join(sorted(s.upper() for s in results["sports_seen"]))
        print(f"    🌐 Multi-Sport Fan — tracking {leagues}")

    print()


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    files = discover_watched_files(root)

    if not files:
        print(f"No watched-games JSON files found under {os.path.abspath(root)}.")
        return

    print(f"Found {len(files)} watched-games file(s):")
    for f in files:
        print(f"  [{f['sport']}] {f['path']}  ({len(f['data'])} games)")

    leagues = build_leagues(root)
    results = compute_awards(files, leagues)
    print_report(results)


if __name__ == "__main__":
    main()
