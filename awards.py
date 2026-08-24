#!/usr/bin/env python3
"""
awards.py
Fan Awards report — scans for watched-games JSON files from ANY sport
tracker in this project (MLB, NBA, college basketball, NFL, college
football, or a future one) and hands out trophies based on how much of the
real schedule you watched.

Deliberately lives outside any single sport's files: it doesn't hardcode
MLB/NBA/college/NFL internals directly. Instead each sport plugs in through
a small adapter in LEAGUES below. Sport support modules (mlb.py,
espn_nba.py, espn_cbb.py, espn_nfl.py, espn_cfb.py, nba_dates.py,
nfl_dates.py) are located dynamically under the scan root — they don't
need to live next to this file (see _import_from_root below).

Note on the "college" tag ambiguity: both the NBA tracker and the NFL
tracker tag their college games with the same "league": "college" key —
one means college basketball, the other college football. There's nothing
in the tag itself to tell them apart, so discover_watched_files() below
disambiguates by which FILE the tag came from: a "college" game inside an
nba-tracker file becomes sport="college" (basketball); inside an
nfl-tracker file it becomes sport="cfb" (football). Untagged records
(saved before college support existed) default to the file's own sport.

Trophies:
  Season Attendance   — Gold (100%) / Silver (75%+) / Bronze (50%+) of a
                         team's REGULAR season games, per team per season.
                         Applies to all five leagues.
  Playoff Series       — MLB & NBA only. One trophy per playoff SERIES you
                         watched every game of (not "every playoff game the
                         team played" — a team's postseason can span several
                         separate series). Shown as e.g.
                         "Celtics vs Mavericks  4-1  Round 4  2023-24".
                         Only awarded once a series has actually clinched
                         (so an in-progress series isn't prematurely
                         credited). MLB round names are exact (from the
                         API's own game-type codes); NBA round names are
                         approximate ordinal labels ("Round 1", "Round 2",
                         ...) since the schedule endpoint used here doesn't
                         reliably expose real round names.
                         NOT computed for football (NFL/college football)
                         — single-elimination playoff brackets don't really
                         have a "series" to watch every game of the way a
                         best-of-7 does, so this is skipped for both
                         football leagues by design (has_series=False).
  March Madness %      — College basketball only, and handled differently
                         on purpose: the NCAA Tournament is
                         single-elimination, so "watched every game of a
                         series" doesn't apply. Instead this reports, per
                         season, what % of a fixed 67-game field (the
                         tournament's size since 2011) you watched — the
                         numerator is every watched college POSTSEASON game
                         (conference tournament + NCAA Tournament combined,
                         deduped across teams so the same game isn't
                         double-counted).
  Iron Fan             — every game, regular + playoff/postseason combined,
                         for one team's season. All five leagues.
  Wire to Wire          — watched a team's regular-season opener AND finale.
                         All five leagues.
  Century Club          — 100+ total games logged across everything.
  Multi-Sport Fan        — logged games in more than one league.

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

# mlb.py / espn_nba.py / espn_cbb.py / nba_dates.py aren't assumed to live
# next to this file — they're located and imported dynamically in
# build_leagues() below, once we know the scan root.
mlb = None
espn_nba = None
espn_cbb = None
espn_nfl = None
espn_cfb = None
nba_dates = None
nfl_dates = None

PLAYOFF_TYPES_MLB = {"F", "D", "L", "W"}   # wild card / division / league / WS
# First team to reach this many wins clinches the series — used to confirm
# a series has actually finished before awarding a Playoff Series trophy.
_MLB_CLINCH = {"F": 2, "D": 3, "L": 4, "W": 4}
_NBA_CLINCH = 4   # every NBA playoff round is best-of-7

_team_id_cache: dict[tuple[str, str], object] = {}


# ── Dynamic module discovery ─────────────────────────────────────────────────

def _find_module_file(root: str, module_name: str) -> str | None:
    matches = glob.glob(os.path.join(root, "**", f"{module_name}.py"), recursive=True)
    return matches[0] if matches else None


def _import_from_root(module_name: str, root: str):
    """Locate {module_name}.py anywhere under root and import it. Returns
    None (rather than raising) if it can't be found or fails to import."""
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
    Find watched-games JSON files under `root` (recursive). Returns a list
    of {"path", "sport", "data"}. A single tracker file can produce
    multiple entries here, split by each game record's "league" tag:
      - an NBA-tracker file ("nba" in the filename) splits into
        sport="nba" and/or sport="college" (college BASKETBALL).
      - an NFL-tracker file ("nfl" in the filename) splits into
        sport="nfl" and/or sport="cfb" (college FOOTBALL).
    Both trackers use the same "college" tag internally, which is why the
    split has to happen per-file rather than globally — the file it came
    from is what disambiguates college hoops from college football.
    Untagged records (saved before college support existed) default to
    the file's own sport ("nba" or "nfl").
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

        base_lower = base.lower()
        if "nfl" in base_lower:
            default_sport, college_bucket = "nfl", "cfb"
        elif "nba" in base_lower:
            default_sport, college_bucket = "nba", "college"
        else:
            default_sport, college_bucket = "mlb", None

        by_league: dict[str, dict] = defaultdict(dict)
        for gid, g in data.items():
            tag = g.get("league", default_sport)
            if tag == "college" and college_bucket:
                sport = college_bucket
            elif tag == default_sport:
                sport = default_sport
            else:
                sport = default_sport   # unrecognized tag — fall back to the file's own sport
            by_league[sport][gid] = g

        for sport, subset in by_league.items():
            label = f"{path} [{sport}]" if len(by_league) > 1 else path
            found.append({"path": label, "sport": sport, "data": subset})

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


def _mlb_team_games(team_id, team_name: str, season: str) -> dict:
    """
    gid(str) -> {kind, date, opponent, round, away_score, home_score,
    team_is_home, game_type} for one team's season. "round" is exact here
    (MLB's game_type code maps directly to a real round name).
    """
    types_to_fetch = ["R"] + sorted(PLAYOFF_TYPES_MLB)
    games = mlb.fetch_season_schedule(team_id, season, game_types=types_to_fetch)
    out = {}
    for g in games:
        gid   = str(g.get("game_id"))
        gtype = g.get("game_type")
        kind  = "regular" if gtype == "R" else "playoff"
        team_is_home = g.get("home_name") == team_name
        opponent = g.get("away_name") if team_is_home else g.get("home_name")
        out[gid] = {
            "kind": kind,
            "date": g.get("game_date", ""),
            "opponent": opponent,
            "round": mlb.GAME_TYPE_LABELS.get(gtype, gtype) if kind == "playoff" else None,
            "away_score": g.get("away_score", ""),
            "home_score": g.get("home_score", ""),
            "team_is_home": team_is_home,
            "game_type": gtype,
        }
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


def _season_end_year(season_label: str) -> str:
    """'2023-24' -> '2024' — the year the season (or its postseason) ends in."""
    start = season_label.split("-")[0]
    return str(int(start) + 1)


def _espn_team_games(module, team_id, team_name: str, season_label: str) -> dict:
    """Shared by NBA and college — same endpoint shape, same parsed fields.
    "round" is left None here (filled in later, per-series, in
    _build_playoff_series — the schedule endpoint doesn't reliably expose
    real round names, unlike MLB's explicit game_type)."""
    param = _season_end_year(season_label)
    reg  = module.fetch_team_schedule(team_id, param, season_types=["2"])
    post = module.fetch_team_schedule(team_id, param, season_types=["3"])
    out = {}
    for kind, games in (("regular", reg), ("playoff", post)):
        for g in games:
            gid = str(g["game_id"])
            team_is_home = g.get("home_name") == team_name
            opponent = g.get("away_name") if team_is_home else g.get("home_name")
            out[gid] = {
                "kind": kind,
                "date": g.get("game_date", ""),
                "opponent": opponent,
                "round": None,
                "away_score": g.get("away_score", ""),
                "home_score": g.get("home_score", ""),
                "team_is_home": team_is_home,
                "game_type": None,
            }
    return out


def _nba_team_games(team_id, team_name: str, season: str) -> dict:
    return _espn_team_games(espn_nba, team_id, team_name, season)


# ── College adapter ────────────────────────────────────────────────────────

def _cbb_find_team_id(name: str):
    key = ("college", name)
    if key in _team_id_cache:
        return _team_id_cache[key]
    tid = None
    try:
        results = espn_cbb.find_teams(name)
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


def _cbb_team_games(team_id, team_name: str, season: str) -> dict:
    return _espn_team_games(espn_cbb, team_id, team_name, season)


# ── NFL / college football adapters ──────────────────────────────────────────
# No Playoff Series trophies for either — has_series=False in build_leagues
# below, per request. Otherwise these plug in exactly like the basketball
# pair above.

def _football_team_games(module, team_id, team_name: str, season: str) -> dict:
    """Same idea as _espn_team_games(), but WITHOUT the season-end-year
    conversion — football seasons are already labeled by the year they
    START in (e.g. '2024'), which is what the API itself expects, unlike
    the NBA/college-hoops '2023-24' hyphenated label."""
    reg  = module.fetch_team_schedule(team_id, season, season_types=["2"])
    post = module.fetch_team_schedule(team_id, season, season_types=["3"])
    out = {}
    for kind, games in (("regular", reg), ("playoff", post)):
        for g in games:
            gid = str(g["game_id"])
            team_is_home = g.get("home_name") == team_name
            opponent = g.get("away_name") if team_is_home else g.get("home_name")
            out[gid] = {
                "kind": kind,
                "date": g.get("game_date", ""),
                "opponent": opponent,
                "round": None,
                "away_score": g.get("away_score", ""),
                "home_score": g.get("home_score", ""),
                "team_is_home": team_is_home,
                "game_type": None,
            }
    return out


def _nfl_find_team_id(name: str):
    key = ("nfl", name)
    if key in _team_id_cache:
        return _team_id_cache[key]
    tid = None
    try:
        results = espn_nfl.find_teams(name)
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


def _nfl_team_games(team_id, team_name: str, season: str) -> dict:
    return _football_team_games(espn_nfl, team_id, team_name, season)


def _cfb_find_team_id(name: str):
    key = ("cfb", name)
    if key in _team_id_cache:
        return _team_id_cache[key]
    tid = None
    try:
        results = espn_cfb.find_teams(name)
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


def _cfb_team_games(team_id, team_name: str, season: str) -> dict:
    return _football_team_games(espn_cfb, team_id, team_name, season)


LEAGUES = {}   # populated by build_leagues()


def build_leagues(root: str) -> dict:
    """Locate and import each sport's support module(s) from under `root`,
    then build the adapter table. Call once per run, before compute_awards."""
    global mlb, espn_nba, espn_cbb, espn_nfl, espn_cfb, nba_dates, nfl_dates, LEAGUES
    mlb       = _import_from_root("mlb", root)
    espn_nba  = _import_from_root("espn_nba", root)
    espn_cbb  = _import_from_root("espn_cbb", root)
    espn_nfl  = _import_from_root("espn_nfl", root)
    espn_cfb  = _import_from_root("espn_cfb", root)
    nba_dates = _import_from_root("nba_dates", root)
    nfl_dates = _import_from_root("nfl_dates", root)

    LEAGUES = {
        "mlb": {
            "available":    mlb is not None,
            "icon":         "⚾",
            "has_series":   True,
            "season_of":    (lambda date: date.split("-")[0]) if mlb else None,
            "find_team_id": _mlb_find_team_id if mlb else None,
            "team_games":   _mlb_team_games if mlb else None,
        },
        "nba": {
            "available":    espn_nba is not None and nba_dates is not None,
            "icon":         "🏀",
            "has_series":   True,
            "season_of":    nba_dates.season_label if nba_dates else None,
            "find_team_id": _nba_find_team_id if espn_nba else None,
            "team_games":   _nba_team_games if espn_nba else None,
        },
        "college": {
            "available":    espn_cbb is not None and nba_dates is not None,
            "icon":         "🎓",
            "has_series":   False,   # single-elimination — see March Madness % instead
            "season_of":    nba_dates.season_label if nba_dates else None,
            "find_team_id": _cbb_find_team_id if espn_cbb else None,
            "team_games":   _cbb_team_games if espn_cbb else None,
        },
        "nfl": {
            "available":    espn_nfl is not None and nfl_dates is not None,
            "icon":         "🏈",
            "has_series":   False,   # no playoff-series trophies for football, by request
            "season_of":    nfl_dates.season_label if nfl_dates else None,
            "find_team_id": _nfl_find_team_id if espn_nfl else None,
            "team_games":   _nfl_team_games if espn_nfl else None,
        },
        "cfb": {
            "available":    espn_cfb is not None and nfl_dates is not None,
            "icon":         "🏈",
            "has_series":   False,   # no playoff-series trophies for football, by request
            "season_of":    nfl_dates.season_label if nfl_dates else None,
            "find_team_id": _cfb_find_team_id if espn_cfb else None,
            "team_games":   _cfb_team_games if espn_cfb else None,
        },
    }
    return LEAGUES


# ── Playoff series trophies (MLB / NBA) ─────────────────────────────────────

def _build_playoff_series(sport: str, team_name: str, season: str, game_map: dict, watched_ids: set) -> list[dict]:
    """
    Group a team's playoff games by opponent (each opponent faced in the
    postseason = one series), then award a trophy for each series where:
      - the series has actually clinched (someone hit the win threshold),
        so an in-progress series isn't prematurely credited, and
      - every game of that (now-finished) series is in watched_ids.
    A lone 1-game group (e.g. a single play-in game) doesn't count as a
    "series" for this trophy — it's excluded.
    """
    playoff = {gid: v for gid, v in game_map.items() if v["kind"] == "playoff"}
    if not playoff:
        return []

    by_opponent: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for gid, v in playoff.items():
        by_opponent[v["opponent"]].append((gid, v))

    series_list = []
    for opponent, glist in by_opponent.items():
        glist.sort(key=lambda gv: gv[1]["date"])
        series_list.append((glist[0][1]["date"], opponent, glist))
    series_list.sort(key=lambda s: s[0])   # chronological, earliest series first

    trophies = []
    for i, (_, opponent, glist) in enumerate(series_list, 1):
        scored = [(gid, v) for gid, v in glist
                  if v["away_score"] not in ("", None) and v["home_score"] not in ("", None)]
        if len(scored) < 2:
            continue   # not a real multi-game series

        team_wins = opp_wins = 0
        for gid, v in scored:
            try:
                a, h = int(v["away_score"]), int(v["home_score"])
            except (TypeError, ValueError):
                continue
            team_score = h if v["team_is_home"] else a
            opp_score  = a if v["team_is_home"] else h
            if team_score > opp_score:
                team_wins += 1
            elif opp_score > team_score:
                opp_wins += 1

        if sport == "mlb":
            gtype = scored[0][1].get("game_type")
            threshold = _MLB_CLINCH.get(gtype, 4)
        else:
            threshold = _NBA_CLINCH

        if max(team_wins, opp_wins) < threshold:
            continue   # series still in progress — no trophy yet

        total_games   = len(scored)
        watched_count = sum(1 for gid, _ in scored if gid in watched_ids)
        if watched_count != total_games:
            continue   # didn't watch every game of this (finished) series

        round_label = scored[0][1].get("round") or f"Round {i}"
        trophies.append({
            "sport": sport, "team": team_name, "opponent": opponent, "season": season,
            "record": f"{team_wins}-{opp_wins}", "round": round_label, "games": total_games,
        })

    return trophies


def _dedupe_series(playoff_series: list[dict]) -> list[dict]:
    """Each series gets built once per team (once from each side), so the
    same series shows up twice — once per perspective. Keep just one entry
    per (sport, season, round, {team, opponent} pair), preferring whichever
    team name sorts first alphabetically so the output is deterministic."""
    best: dict[tuple, dict] = {}
    for s in playoff_series:
        key = (s["sport"], s["season"], s["round"], frozenset([s["team"], s["opponent"]]))
        current = best.get(key)
        if current is None or s["team"] < current["team"]:
            best[key] = s
    return list(best.values())


# ── March Madness % (college) ────────────────────────────────────────────────

# The NCAA Tournament field has been 68 teams (67 games) since 2011 — fixed
# denominator, no need to approximate or fetch a national schedule for it.
MARCH_MADNESS_TOTAL_GAMES = 67


def _build_march_madness(mm_watched_by_season: dict) -> list[dict]:
    """
    Turn the per-season sets of watched college POSTSEASON game ids
    (deduped across every team — the same game appears in two teams'
    buckets, so a plain set union handles that) into a national
    Gold/Silver/Bronze percentage. Every postseason college game counted
    here (conference tournament + NCAA Tournament, per how the college
    adapter classifies "playoff") — no attempt to separate the two, on the
    reasoning that conference tournament games ARE tournament basketball
    too, and it avoids fragile date-window guessing.
    """
    results = []
    for season, watched_ids in sorted(mm_watched_by_season.items()):
        watched_n = len(watched_ids)
        if watched_n == 0:
            continue
        pct = watched_n / MARCH_MADNESS_TOTAL_GAMES
        tier = "gold" if pct >= 1.0 else "silver" if pct >= 0.75 else "bronze" if pct >= 0.5 else None
        if tier:
            results.append({
                "season": season, "watched": watched_n, "total": MARCH_MADNESS_TOTAL_GAMES,
                "pct": pct, "tier": tier,
            })
    return results


# ── Computation ────────────────────────────────────────────────────────────

def compute_awards(files: list[dict]) -> dict:
    """Cross-check every team/season a person has watched games for against
    the real schedule, and return the awards they qualify for."""
    buckets: dict[tuple[str, str, str], set] = defaultdict(set)  # (sport,team,season) -> watched gids
    total_watched = 0
    sports_seen: set[str] = set()

    for entry in files:
        sport  = entry["sport"]
        league = LEAGUES.get(sport)
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

    trophies, playoff_series, iron_fan, wire_to_wire = [], [], [], []
    mm_watched_by_season: dict[str, set] = defaultdict(set)

    print(f"\nChecking {len(buckets)} team/season combination(s) against real schedules...\n")
    for (sport, team_name, season), watched_ids in sorted(buckets.items()):
        league  = LEAGUES[sport]
        team_id = league["find_team_id"](team_name)
        if team_id is None:
            print(f"  {league['icon']} {team_name} — couldn't resolve team ID, skipping.")
            continue

        print(f"  {league['icon']} {team_name} — {season}...")
        try:
            game_map = league["team_games"](team_id, team_name, season)
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

        # Season attendance trophy (regular season only) — all three leagues
        if regular_ids:
            pct = len(watched_regular) / len(regular_ids)
            tier = "gold" if pct >= 1.0 else "silver" if pct >= 0.75 else "bronze" if pct >= 0.5 else None
            if tier:
                trophies.append({
                    "sport": sport, "team": team_name, "season": season, "tier": tier,
                    "watched": len(watched_regular), "total": len(regular_ids), "pct": pct,
                })

        # Playoff Series trophies — MLB & NBA only (college is single-elim, see March Madness %)
        if league["has_series"]:
            playoff_series.extend(_build_playoff_series(sport, team_name, season, game_map, watched_ids))
        elif sport == "college":
            # No series concept — feed watched postseason games into the
            # March Madness % instead. A set union naturally dedupes the
            # same game showing up once per team (home + away buckets).
            mm_watched_by_season[season] |= watched_playoff

        # Iron Fan — every game, regular + playoff/postseason combined
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
        "playoff_series": _dedupe_series(playoff_series),
        "march_madness": _build_march_madness(mm_watched_by_season),
        "iron_fan": iron_fan,
        "wire_to_wire": wire_to_wire,
        "total_watched": total_watched,
        "sports_seen": sports_seen,
    }


# ── Report ─────────────────────────────────────────────────────────────────

_TIER_ICON  = {"gold": "🥇", "silver": "🥈", "bronze": "🥉"}
_TIER_LABEL = {"gold": "Gold — 100%", "silver": "Silver — 75%+", "bronze": "Bronze — 50%+"}
_TIER_RANK  = {"gold": 3, "silver": 2, "bronze": 1}
_SPORT_ICON = {"mlb": "⚾", "nba": "🏀", "college": "🎓", "nfl": "🏈", "cfb": "🏈"}
_SPORT_NAME = {"mlb": "MLB", "nba": "NBA", "college": "College Bball", "nfl": "NFL", "cfb": "College FB"}


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

    if results["playoff_series"]:
        print("\n  🏆 Playoff Series Watched\n")
        for s in sorted(results["playoff_series"], key=lambda s: (s["sport"], s["season"], s["team"])):
            icon = _SPORT_ICON.get(s["sport"], "")
            print(f"    {icon} {s['team']} vs {s['opponent']}   {s['record']}   {s['round']}   {s['season']}")

    if results["march_madness"]:
        print("\n  🎓 March Madness Watched (national, all teams combined)\n")
        for m in results["march_madness"]:
            print(f"    {_TIER_ICON[m['tier']]} {m['season']}   "
                  f"{m['watched']}/{m['total']} games ({m['pct']*100:.0f}%)   [{_TIER_LABEL[m['tier']]}]")

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
        leagues = ", ".join(_SPORT_NAME.get(s, s.upper()) for s in sorted(results["sports_seen"]))
        print(f"    🌐 Multi-Sport Fan — tracking {leagues}")

    print()


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    files = discover_watched_files(root)

    if not files:
        print(f"No watched-games JSON files found under {os.path.abspath(root)}.")
        return

    print(f"Found {len(files)} watched-games bucket(s):")
    for f in files:
        print(f"  [{f['sport']}] {f['path']}  ({len(f['data'])} games)")

    build_leagues(root)
    results = compute_awards(files)
    print_report(results)


if __name__ == "__main__":
    main()
