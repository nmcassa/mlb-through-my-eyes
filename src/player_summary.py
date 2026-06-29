"""
player_summary.py
Aggregates per-player pitching and batting stats across a set of watched games.

Pitching stats computed:
  ERA, WHIP, K/9, BB/9, HR/9
  (derived from raw counting stats: IP, ER, H, BB, K, HR)

Batting stats computed:
  AVG, OBP, SLG, OPS
  (derived from AB, H, BB, HBP, SF, TB; PA = AB + BB + HBP + SF)

Data is stored per-player per-game so that season and team filters can be
applied in memory without re-fetching from the API.
"""
from __future__ import annotations

import mlb


# ── IP helpers ────────────────────────────────────────────────────────────────

def ip_to_outs(ip_str: str) -> int:
    """Convert an innings-pitched string like '6.2' into a whole-out count."""
    try:
        parts = str(ip_str).split(".")
        return int(parts[0]) * 3 + (int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return 0


def outs_to_ip(outs: int) -> str:
    """Convert a whole-out count back to a display IP string like '6.2'."""
    return f"{outs // 3}.{outs % 3}"


# ── Data collection ───────────────────────────────────────────────────────────

def collect_player_game_stats(watched: dict) -> tuple[dict, dict]:
    """
    Fetch boxscore data for every watched game and store per-player, per-game
    stats. Returns two dicts keyed by player name:

      pitchers[name] = {
          "games": [ { "game_id", "season", "team", outs, er, h, bb, k, hr } ],
      }
      batters[name] = {
          "games": [ { "game_id", "season", "team", ab, h, bb, hbp, sf, tb, pa } ],
      }

    All filtering and aggregation happens downstream from these raw records,
    so no re-fetch is needed when the user changes season/team filters.
    """
    pitchers: dict[str, dict] = {}
    batters:  dict[str, dict] = {}

    game_ids = list(watched.keys())
    total    = len(game_ids)

    for i, gid in enumerate(game_ids, 1):
        game   = watched[gid]
        season = game["date"][:4]
        print(f"  Fetching game {i}/{total}: {game['date']}  {game['away']} @ {game['home']}...")
        try:
            data = mlb.fetch_boxscore_data(int(game["game_id"]))
        except RuntimeError as e:
            print(f"    Warning: {e} — skipping.")
            continue

        for side in ("away", "home"):
            team_name = game["away"] if side == "away" else game["home"]
            players   = data.get(side, {}).get("players", {})

            for pid, p in players.items():
                name          = p.get("person", {}).get("fullName", pid)
                game_batting  = p.get("stats", {}).get("batting",  {})
                game_pitching = p.get("stats", {}).get("pitching", {})

                # ── Pitching ──────────────────────────────────────────────
                if game_pitching.get("inningsPitched") not in (None, "", "0.0", 0):
                    person_id = int(pid.lstrip("ID")) if pid.startswith("ID") else None
                    pitchers.setdefault(name, {"person_id": person_id, "games": []})
                    pitchers[name]["games"].append({
                        "game_id": gid,
                        "season":  season,
                        "team":    team_name,
                        "outs":    ip_to_outs(game_pitching.get("inningsPitched", 0)),
                        "er":      int(game_pitching.get("earnedRuns",  0)),
                        "h":       int(game_pitching.get("hits",        0)),
                        "bb":      int(game_pitching.get("baseOnBalls", 0)),
                        "k":       int(game_pitching.get("strikeOuts",  0)),
                        "hr":      int(game_pitching.get("homeRuns",    0)),
                    })

                # ── Batting ───────────────────────────────────────────────
                ab = int(game_batting.get("atBats", 0))
                if ab > 0:
                    bb  = int(game_batting.get("baseOnBalls", 0))
                    hbp = int(game_batting.get("hitByPitch",  0))
                    sf  = int(game_batting.get("sacFlies",    0))
                    h   = int(game_batting.get("hits",        0))
                    dbl = int(game_batting.get("doubles",     0))
                    trp = int(game_batting.get("triples",     0))
                    hr  = int(game_batting.get("homeRuns",    0))
                    tb  = (h - dbl - trp - hr) + 2*dbl + 3*trp + 4*hr

                    person_id = int(pid.lstrip("ID")) if pid.startswith("ID") else None
                    batters.setdefault(name, {"person_id": person_id, "games": []})
                    batters[name]["games"].append({
                        "game_id": gid,
                        "season":  season,
                        "team":    team_name,
                        "ab":      ab,
                        "h":       h,
                        "bb":      bb,
                        "hbp":     hbp,
                        "sf":      sf,
                        "tb":      tb,
                        "pa":      ab + bb + hbp + sf,
                    })

    return pitchers, batters


# ── In-memory filtering & aggregation ────────────────────────────────────────

def _aggregate_pitcher(name: str, game_rows: list[dict]) -> dict:
    """Sum raw pitching counting stats across a list of filtered game records."""
    acc = {"outs": 0, "er": 0, "h": 0, "bb": 0, "k": 0, "hr": 0, "appearances": 0, "teams": {}}
    for g in game_rows:
        acc["outs"]        += g["outs"]
        acc["er"]          += g["er"]
        acc["h"]           += g["h"]
        acc["bb"]          += g["bb"]
        acc["k"]           += g["k"]
        acc["hr"]          += g["hr"]
        acc["appearances"] += 1
        acc["teams"][g["team"]] = acc["teams"].get(g["team"], 0) + 1
    return acc


def _aggregate_batter(name: str, game_rows: list[dict]) -> dict:
    """Sum raw batting counting stats across a list of filtered game records."""
    acc = {"ab": 0, "h": 0, "bb": 0, "hbp": 0, "sf": 0, "tb": 0, "pa": 0, "appearances": 0, "teams": {}}
    for g in game_rows:
        acc["ab"]          += g["ab"]
        acc["h"]           += g["h"]
        acc["bb"]          += g["bb"]
        acc["hbp"]         += g["hbp"]
        acc["sf"]          += g["sf"]
        acc["tb"]          += g["tb"]
        acc["pa"]          += g["pa"]
        acc["appearances"] += 1
        acc["teams"][g["team"]] = acc["teams"].get(g["team"], 0) + 1
    return acc


def _primary_team(teams_dict: dict) -> str:
    """Return the team a player appeared for most across watched games."""
    if not teams_dict:
        return "—"
    return max(teams_dict, key=teams_dict.get)


def _all_teams_display(teams_dict: dict) -> str:
    """
    Return a display string listing all teams a player appeared for,
    sorted by appearance count descending. Used in unfiltered views.
    e.g. "Atlanta Braves / Los Angeles Dodgers"
    """
    if not teams_dict:
        return "—"
    sorted_teams = sorted(teams_dict, key=teams_dict.get, reverse=True)
    return " / ".join(sorted_teams)


def filter_and_aggregate(
    pitchers: dict,
    batters:  dict,
    season_filter: str | None = None,
    team_filter:   str | None = None,
) -> tuple[dict, dict]:
    """
    Apply season and team filters entirely in memory — no API calls.

    season_filter: if set, only include game records from that year.
    team_filter:   if set, only include game records where the player's
                   team for that game matches exactly — so a player who
                   appeared for multiple teams only shows their stats
                   from games while on that specific team.

    When team_filter is None: players who appeared for multiple teams
    get ONE row per team, keyed as "Name (Team)" so their stats from
    each team context are shown separately rather than merged together.

    Returns aggregated (pitchers_raw, batters_raw) dicts keyed by a
    unique "display key" (player name, or "Name (Team)" for multi-teamers).
    """
    def keep(g: dict) -> bool:
        if season_filter and g["season"] != season_filter:
            return False
        if team_filter and g["team"] != team_filter:
            return False
        return True

    def split_by_team(name: str, games: list[dict], person_id) -> dict[str, dict]:
        """
        If the player appeared for multiple teams, return one aggregated
        dict per team keyed as "Name (Team)".
        If only one team, return a single entry keyed by plain name.
        """
        by_team: dict[str, list] = {}
        for g in games:
            by_team.setdefault(g["team"], []).append(g)

        if len(by_team) <= 1:
            # Single team — use plain name as key
            team = next(iter(by_team)) if by_team else "—"
            return {name: (games, person_id, team)}
        else:
            # Multiple teams — split into separate keyed rows
            result = {}
            for team, tgames in by_team.items():
                key = f"{name} ({team})"
                result[key] = (tgames, person_id, team)
            return result

    filtered_pitchers: dict[str, dict] = {}
    for name, data in pitchers.items():
        matching = [g for g in data["games"] if keep(g)]
        if not matching:
            continue
        if team_filter:
            # Single team context — aggregate all matching records together
            agg = _aggregate_pitcher(name, matching)
            agg["person_id"] = data.get("person_id")
            filtered_pitchers[name] = agg
        else:
            # No team filter — split multi-team players by team
            for key, (games, pid, team) in split_by_team(name, matching, data.get("person_id")).items():
                agg = _aggregate_pitcher(name, games)
                agg["person_id"] = pid
                agg["display_team"] = team   # override _primary_team in calc step
                filtered_pitchers[key] = agg

    filtered_batters: dict[str, dict] = {}
    for name, data in batters.items():
        matching = [g for g in data["games"] if keep(g)]
        if not matching:
            continue
        if team_filter:
            agg = _aggregate_batter(name, matching)
            agg["person_id"] = data.get("person_id")
            filtered_batters[name] = agg
        else:
            for key, (games, pid, team) in split_by_team(name, matching, data.get("person_id")).items():
                agg = _aggregate_batter(name, games)
                agg["person_id"] = pid
                agg["display_team"] = team
                filtered_batters[key] = agg

    return filtered_pitchers, filtered_batters


# ── Stat calculators ──────────────────────────────────────────────────────────

def calc_pitching_stats(name: str, raw: dict) -> dict:
    """Derive ERA, WHIP, K/9, BB/9, HR/9 from aggregated raw counting stats."""
    outs = raw["outs"]
    ip   = outs / 3

    base = {
        "name":      name,
        "person_id": raw.get("person_id"),
        "team":      raw.get("display_team") or _primary_team(raw.get("teams", {})),
        "app":       raw["appearances"],
        "ip":        outs_to_ip(outs),
        "_outs":     outs,
        "_era": 999.0, "_whip": 999.0, "_k9": 0.0, "_bb9": 999.0, "_hr9": 999.0,
    }

    if ip == 0:
        return {**base, "era": "—", "whip": "—", "k9": "—", "bb9": "—", "hr9": "—"}

    era  = (raw["er"] / ip) * 9
    whip = (raw["h"] + raw["bb"]) / ip
    k9   = (raw["k"]  / ip) * 9
    bb9  = (raw["bb"] / ip) * 9
    hr9  = (raw["hr"] / ip) * 9

    return {**base,
        "era":  f"{era:.2f}",  "_era":  era,
        "whip": f"{whip:.3f}", "_whip": whip,
        "k9":   f"{k9:.1f}",   "_k9":   k9,
        "bb9":  f"{bb9:.1f}",  "_bb9":  bb9,
        "hr9":  f"{hr9:.2f}",  "_hr9":  hr9,
    }


def calc_batting_stats(name: str, raw: dict) -> dict:
    """Derive AVG, OBP, SLG, OPS from aggregated raw counting stats."""
    ab  = raw["ab"];  h   = raw["h"];  bb  = raw["bb"]
    hbp = raw["hbp"]; sf  = raw["sf"]; tb  = raw["tb"]
    pa  = raw["pa"]

    avg       = h / ab if ab > 0 else 0
    obp_denom = ab + bb + hbp + sf
    obp       = (h + bb + hbp) / obp_denom if obp_denom > 0 else 0
    slg       = tb / ab if ab > 0 else 0
    ops       = obp + slg

    return {
        "name":      name,
        "person_id": raw.get("person_id"),
        "team":      raw.get("display_team") or _primary_team(raw.get("teams", {})),
        "app":       raw["appearances"],
        "ab":   ab,
        "pa":   pa,
        "h":    h,
        "avg":  f"{avg:.3f}", "_avg": avg,
        "obp":  f"{obp:.3f}", "_obp": obp,
        "slg":  f"{slg:.3f}", "_slg": slg,
        "ops":  f"{ops:.3f}", "_ops": ops,
    }


# ── Leaderboard builders ──────────────────────────────────────────────────────

MIN_PITCHER_OUTS = 3   # at least 1 IP to appear
MIN_BATTER_PA    = 5   # at least 5 PA to appear (replaces AB threshold)


def pitching_leaderboard(pitchers_raw: dict, ip_min: float | None = None) -> list[dict]:
    """
    Return qualifying pitchers with computed stats. No sort applied.
    ip_min: optional minimum IP (float, e.g. 5.0); overrides MIN_PITCHER_OUTS.
    """
    outs_threshold = int(ip_min * 3) if ip_min is not None else MIN_PITCHER_OUTS
    rows = []
    for name, raw in pitchers_raw.items():
        if raw["outs"] < outs_threshold:
            continue
        rows.append(calc_pitching_stats(name, raw))
    return rows


def batting_leaderboard(batters_raw: dict, pa_min: int | None = None) -> list[dict]:
    """
    Return qualifying batters with computed stats. No sort applied.
    pa_min: optional minimum PA; overrides MIN_BATTER_PA.
    """
    threshold = pa_min if pa_min is not None else MIN_BATTER_PA
    rows = []
    for name, raw in batters_raw.items():
        if raw["pa"] < threshold:
            continue
        rows.append(calc_batting_stats(name, raw))
    return rows
