"""
comparison.py
"My Small Sample" — compares a player's stats in the user's watched games
against their full season or full career stats from the MLB API.

For each player the screen shows three rows of rate stats:
  WATCHED  — computed from boxscore data across watched games
  REF      — career or season average from the API
  DELTA    — watched minus ref

The reference type (season vs career) is determined by whether a season
filter is active:
  - season filter set  → compare against that season's stats
  - no season filter   → compare against career stats

player_stat_data() response shape
----------------------------------
data["stats"] is a list of blocks. Each block looks like:
  {
    "type":   "career",          # plain string
    "group":  "pitching",        # plain string
    "stat":   { ... totals ... } # the aggregate stat dict (career / season totals)
    "splits": [ ... ]            # list of per-team/year splits; may be empty for career
  }
For career stats the totals live in block["stat"].
For season stats the totals also live in block["stat"] when there is only one
team, or we sum across block["splits"] when the player changed teams mid-season.
"""
from __future__ import annotations

import mlb
import player_summary as ps


# ── Raw stat extraction ───────────────────────────────────────────────────────

def _extract_stat_dict(data: dict, stat_type: str) -> dict | None:
    """
    Pull the aggregate stat dict from a player_stat_data() response.

    For career:  block["stat"] is the career aggregate.
    For season:  block["stat"] is the season aggregate (or we sum splits if
                 the player was on multiple teams).
    Returns None if nothing usable is found.
    """
    stats_list = data.get("stats", [])
    for block in stats_list:
        if not isinstance(block, dict):
            continue
        # Match on the type string directly
        block_type = block.get("type", "")
        if isinstance(block_type, dict):
            block_type = block_type.get("displayName", "")
        if block_type.lower() != stat_type.lower():
            continue

        # Prefer the top-level aggregate stat dict
        if "stat" in block and block["stat"]:
            return block["stat"]

        # Fall back to first split
        splits = block.get("splits", [])
        if splits:
            return splits[0].get("stat", {})

    # If we never matched the type string, just take the first block with data
    for block in stats_list:
        if not isinstance(block, dict):
            continue
        if "stat" in block and block["stat"]:
            return block["stat"]
        splits = block.get("splits", [])
        if splits:
            return splits[0].get("stat", {})

    return None


# ── Reference stat fetching ───────────────────────────────────────────────────

def _fetch_pitcher_ref(person_id: int, season: str | None) -> dict | None:
    """
    Fetch ERA, WHIP, K/9, BB/9, HR/9 from the API for a pitcher.
    Returns a flat dict of display + numeric values, or None on failure.
    """
    stat_type = "season" if season else "career"
    try:
        data = mlb.fetch_player_stat_data(person_id, "pitching", stat_type, season=season)
    except RuntimeError:
        return None

    s = _extract_stat_dict(data, stat_type)
    if not s:
        return None
    return _parse_pitcher_stat(s)


def _parse_pitcher_stat(s: dict) -> dict | None:
    """Derive rate stats from a raw pitching stat dict."""
    try:
        ip_str = s.get("inningsPitched") or "0.0"
        outs   = ps.ip_to_outs(str(ip_str))
        ip     = outs / 3
        if ip == 0:
            return None

        h  = float(s.get("hits",        0) or 0)
        bb = float(s.get("baseOnBalls", 0) or 0)
        er = float(s.get("earnedRuns",  0) or 0)
        k  = float(s.get("strikeOuts",  0) or 0)
        hr = float(s.get("homeRuns",    0) or 0)

        era  = (er / ip) * 9
        whip = (h + bb) / ip
        k9   = (k  / ip) * 9
        bb9  = (bb / ip) * 9
        hr9  = (hr / ip) * 9

        return {
            "ip":   ip_str,
            "era":  f"{era:.2f}",  "_era":  era,
            "whip": f"{whip:.3f}", "_whip": whip,
            "k9":   f"{k9:.1f}",   "_k9":   k9,
            "bb9":  f"{bb9:.1f}",  "_bb9":  bb9,
            "hr9":  f"{hr9:.2f}",  "_hr9":  hr9,
        }
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _fetch_batter_ref(person_id: int, season: str | None) -> dict | None:
    """
    Fetch AVG, OBP, SLG, OPS from the API for a batter.
    Returns a flat dict of display + numeric values, or None on failure.
    """
    stat_type = "season" if season else "career"
    try:
        data = mlb.fetch_player_stat_data(person_id, "hitting", stat_type, season=season)
    except RuntimeError:
        return None

    s = _extract_stat_dict(data, stat_type)
    if not s:
        return None
    return _parse_batter_stat(s)


def _parse_batter_stat(s: dict) -> dict | None:
    """Derive rate stats from a raw hitting stat dict."""
    try:
        avg = float(s.get("avg", 0) or 0)
        obp = float(s.get("obp", 0) or 0)
        slg = float(s.get("slg", 0) or 0)
        ops = float(s.get("ops", 0) or 0)
        pa  = int(s.get("plateAppearances", 0) or 0)
        ab  = int(s.get("atBats",           0) or 0)

        if avg == 0 and obp == 0 and slg == 0:
            return None   # genuinely empty record

        return {
            "pa":  pa,
            "ab":  ab,
            "avg": f"{avg:.3f}", "_avg": avg,
            "obp": f"{obp:.3f}", "_obp": obp,
            "slg": f"{slg:.3f}", "_slg": slg,
            "ops": f"{ops:.3f}", "_ops": ops,
        }
    except (TypeError, ValueError):
        return None


# ── Delta formatting ──────────────────────────────────────────────────────────

def _fmt_delta_stat(
    watched: float | None,
    ref: float | None,
    higher_is_better: bool,
    fmt: str = ".2f",
) -> str:
    if watched is None or ref is None:
        return "—"
    d     = watched - ref
    sign  = "+" if d >= 0 else "-"
    arrow = "▲" if d > 0 else ("▼" if d < 0 else "─")
    return f"{arrow}{sign}{abs(d):{fmt}}"


# ── Row builders ──────────────────────────────────────────────────────────────

def build_pitcher_rows(
    pitchers_raw: dict,
    ip_min: float | None,
    season_filter: str | None,
) -> list[dict]:
    """
    For each qualifying pitcher fetch reference stats and build a comparison row.
    Prints progress to stdout. Only fetches players that pass ip_min threshold.
    """
    leaderboard = ps.pitching_leaderboard(pitchers_raw, ip_min=ip_min)
    rows  = []
    total = len(leaderboard)

    for i, w in enumerate(leaderboard, 1):
        pid = w.get("person_id")
        print(f"  [{i}/{total}] {w['name']}...")
        ref = _fetch_pitcher_ref(pid, season_filter) if pid else None

        rows.append({
            "name":   w["name"],
            "team":   w["team"],
            "app":    w["app"],
            # watched
            "w_ip":   w["ip"],
            "w_era":  w["era"],  "_w_era":  w["_era"],
            "w_whip": w["whip"], "_w_whip": w["_whip"],
            "w_k9":   w["k9"],   "_w_k9":   w["_k9"],
            "w_bb9":  w["bb9"],  "_w_bb9":  w["_bb9"],
            "w_hr9":  w["hr9"],  "_w_hr9":  w["_hr9"],
            # reference
            "r_era":  ref["era"]  if ref else "—",
            "r_whip": ref["whip"] if ref else "—",
            "r_k9":   ref["k9"]   if ref else "—",
            "r_bb9":  ref["bb9"]  if ref else "—",
            "r_hr9":  ref["hr9"]  if ref else "—",
            # delta
            "d_era":  _fmt_delta_stat(w["_era"],  ref["_era"]  if ref else None, False),
            "d_whip": _fmt_delta_stat(w["_whip"], ref["_whip"] if ref else None, False),
            "d_k9":   _fmt_delta_stat(w["_k9"],   ref["_k9"]   if ref else None, True,  ".1f"),
            "d_bb9":  _fmt_delta_stat(w["_bb9"],  ref["_bb9"]  if ref else None, False, ".1f"),
            "d_hr9":  _fmt_delta_stat(w["_hr9"],  ref["_hr9"]  if ref else None, False),
        })

    return rows


def build_batter_rows(
    batters_raw: dict,
    pa_min: int | None,
    season_filter: str | None,
) -> list[dict]:
    """
    For each qualifying batter fetch reference stats and build a comparison row.
    Prints progress to stdout. Only fetches players that pass pa_min threshold.
    """
    leaderboard = ps.batting_leaderboard(batters_raw, pa_min=pa_min)
    rows  = []
    total = len(leaderboard)

    for i, w in enumerate(leaderboard, 1):
        pid = w.get("person_id")
        print(f"  [{i}/{total}] {w['name']}...")
        ref = _fetch_batter_ref(pid, season_filter) if pid else None

        rows.append({
            "name":  w["name"],
            "team":  w["team"],
            "app":   w["app"],
            # watched
            "w_pa":  w["pa"],
            "w_ab":  w["ab"],
            "w_avg": w["avg"], "_w_avg": w["_avg"],
            "w_obp": w["obp"], "_w_obp": w["_obp"],
            "w_slg": w["slg"], "_w_slg": w["_slg"],
            "w_ops": w["ops"], "_w_ops": w["_ops"],
            # reference
            "r_avg": ref["avg"] if ref else "—",
            "r_obp": ref["obp"] if ref else "—",
            "r_slg": ref["slg"] if ref else "—",
            "r_ops": ref["ops"] if ref else "—",
            # delta
            "d_avg": _fmt_delta_stat(w["_avg"], ref["_avg"] if ref else None, True, ".3f"),
            "d_obp": _fmt_delta_stat(w["_obp"], ref["_obp"] if ref else None, True, ".3f"),
            "d_slg": _fmt_delta_stat(w["_slg"], ref["_slg"] if ref else None, True, ".3f"),
            "d_ops": _fmt_delta_stat(w["_ops"], ref["_ops"] if ref else None, True, ".3f"),
        })

    return rows
