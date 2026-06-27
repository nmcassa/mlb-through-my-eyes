"""
player_summary.py
Aggregates per-player pitching and batting stats across a set of watched games.

Pitching stats computed:
  ERA, WHIP, K/9, BB/9, HR/9
  (all derived from raw counting stats: IP, ER, H, BB, K, HR)

Batting stats computed:
  AVG, OBP, SLG, OPS
  (derived from AB, H, BB, HBP, SF, TB)

All stats are accumulated from game-level data so the numbers reflect
only the games the user has watched, not full-season totals.
"""
from __future__ import annotations

import mlb


# ── IP helpers ────────────────────────────────────────────────────────────────

def ip_to_outs(ip_str: str) -> int:
    """Convert an innings-pitched string like '6.2' into a whole-out count."""
    try:
        parts = str(ip_str).split(".")
        full_innings = int(parts[0])
        extra_outs = int(parts[1]) if len(parts) > 1 else 0
        return full_innings * 3 + extra_outs
    except (ValueError, IndexError):
        return 0


def outs_to_ip(outs: int) -> str:
    """Convert a whole-out count back to a display IP string like '6.2'."""
    return f"{outs // 3}.{outs % 3}"


# ── Data collection ───────────────────────────────────────────────────────────

def collect_player_game_stats(watched: dict) -> tuple[dict, dict]:
    """
    Fetch boxscore data for every watched game and accumulate raw counting
    stats per player.

    Returns:
        pitchers: { player_name: { outs, er, h, bb, k, hr, appearances, teams } }
        batters:  { player_name: { ab, h, bb, hbp, sf, tb, appearances, teams } }

    'teams' is a dict of { team_name: appearance_count } used to pick the
    most-seen team for display.
    """
    pitchers: dict[str, dict] = {}
    batters: dict[str, dict] = {}

    game_ids = list(watched.keys())
    total = len(game_ids)

    for i, gid in enumerate(game_ids, 1):
        game = watched[gid]
        print(f"  Fetching game {i}/{total}: {game['date']}  {game['away']} @ {game['home']}...")
        try:
            data = mlb.fetch_boxscore_data(int(game["game_id"]))
        except RuntimeError as e:
            print(f"    Warning: {e} — skipping.")
            continue

        for side in ("away", "home"):
            team_name = game["away"] if side == "away" else game["home"]
            players = data.get(side, {}).get("players", {})

            for pid, p in players.items():
                name = p.get("person", {}).get("fullName", pid)
                game_batting  = p.get("stats", {}).get("batting", {})
                game_pitching = p.get("stats", {}).get("pitching", {})

                # ── Pitching ──────────────────────────────────────────────
                if game_pitching.get("inningsPitched") not in (None, "", "0.0", 0):
                    if name not in pitchers:
                        pitchers[name] = {"outs": 0, "er": 0, "h": 0, "bb": 0,
                                          "k": 0, "hr": 0, "appearances": 0, "teams": {}}
                    acc = pitchers[name]
                    acc["outs"]        += ip_to_outs(game_pitching.get("inningsPitched", 0))
                    acc["er"]          += int(game_pitching.get("earnedRuns", 0))
                    acc["h"]           += int(game_pitching.get("hits", 0))
                    acc["bb"]          += int(game_pitching.get("baseOnBalls", 0))
                    acc["k"]           += int(game_pitching.get("strikeOuts", 0))
                    acc["hr"]          += int(game_pitching.get("homeRuns", 0))
                    acc["appearances"] += 1
                    acc["teams"][team_name] = acc["teams"].get(team_name, 0) + 1

                # ── Batting ───────────────────────────────────────────────
                if game_batting.get("atBats") not in (None, "", 0):
                    if name not in batters:
                        batters[name] = {"ab": 0, "h": 0, "bb": 0, "hbp": 0,
                                         "sf": 0, "tb": 0, "appearances": 0, "teams": {}}
                    acc = batters[name]
                    acc["ab"]          += int(game_batting.get("atBats", 0))
                    acc["h"]           += int(game_batting.get("hits", 0))
                    acc["bb"]          += int(game_batting.get("baseOnBalls", 0))
                    acc["hbp"]         += int(game_batting.get("hitByPitch", 0))
                    acc["sf"]          += int(game_batting.get("sacFlies", 0))
                    singles = (int(game_batting.get("hits", 0))
                               - int(game_batting.get("doubles", 0))
                               - int(game_batting.get("triples", 0))
                               - int(game_batting.get("homeRuns", 0)))
                    tb = (singles
                          + 2 * int(game_batting.get("doubles", 0))
                          + 3 * int(game_batting.get("triples", 0))
                          + 4 * int(game_batting.get("homeRuns", 0)))
                    acc["tb"]          += tb
                    acc["appearances"] += 1
                    acc["teams"][team_name] = acc["teams"].get(team_name, 0) + 1

    return pitchers, batters


def _primary_team(teams_dict: dict) -> str:
    """Return the team name a player appeared for most across watched games."""
    if not teams_dict:
        return "—"
    return max(teams_dict, key=teams_dict.get)


# ── Stat calculators ──────────────────────────────────────────────────────────

def calc_pitching_stats(name: str, raw: dict) -> dict:
    """Derive ERA, WHIP, K/9, BB/9, HR/9 from raw counting stats."""
    outs = raw["outs"]
    ip   = outs / 3

    base = {
        "name": name,
        "team": _primary_team(raw.get("teams", {})),
        "app":  raw["appearances"],
        "ip":   outs_to_ip(outs),
        # numeric shadow values for sorting (never displayed)
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
    """Derive AVG, OBP, SLG, OPS from raw counting stats."""
    ab  = raw["ab"]
    h   = raw["h"]
    bb  = raw["bb"]
    hbp = raw["hbp"]
    sf  = raw["sf"]
    tb  = raw["tb"]

    avg = h / ab if ab > 0 else 0
    obp_denom = ab + bb + hbp + sf
    obp = (h + bb + hbp) / obp_denom if obp_denom > 0 else 0
    slg = tb / ab if ab > 0 else 0
    ops = obp + slg

    return {
        "name": name,
        "team": _primary_team(raw.get("teams", {})),
        "app":  raw["appearances"],
        "ab":   ab,
        "h":    h,
        "avg":  f"{avg:.3f}", "_avg": avg,
        "obp":  f"{obp:.3f}", "_obp": obp,
        "slg":  f"{slg:.3f}", "_slg": slg,
        "ops":  f"{ops:.3f}", "_ops": ops,
    }


# ── Leaderboard builders (unsorted — caller decides order) ────────────────────

MIN_PITCHER_OUTS = 3   # at least 1 IP to appear in pitching summary
MIN_BATTER_AB    = 5   # at least 5 AB to appear in batting summary


def pitching_leaderboard(pitchers: dict) -> list[dict]:
    """Return all qualifying pitchers with computed stats. No sort applied."""
    rows = []
    for name, raw in pitchers.items():
        if raw["outs"] < MIN_PITCHER_OUTS:
            continue
        rows.append(calc_pitching_stats(name, raw))
    return rows


def batting_leaderboard(batters: dict) -> list[dict]:
    """Return all qualifying batters with computed stats. No sort applied."""
    rows = []
    for name, raw in batters.items():
        if raw["ab"] < MIN_BATTER_AB:
            continue
        rows.append(calc_batting_stats(name, raw))
    return rows
