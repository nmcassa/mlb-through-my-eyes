"""
nfl_player_summary.py
Aggregates per-player box score stats across watched games — spanning BOTH
the NFL and college football, same combined-career idea as the basketball
tracker's nba_player_summary.py. Each watched game carries a "league" tag
("nfl" or "college") set by nfl_main.py; games missing the tag default to
"nfl" for backward compatibility.

Unlike the basketball/baseball trackers, this one tracks THREE separate
stat pools rather than one (or two) — QB (passing), Rushing, and
Receiving — mirroring the pitcher/batter split in the MLB tracker. A
player only shows up in a pool if they recorded a stat in that category in
a given game; a rushing QB shows up in both the QB and Rushing pools with
independent per-pool aggregates, which is the correct behavior (their
rushing yards shouldn't affect their passer rating and vice versa).

Rate stats derived from aggregated totals (not per-game averages, so
completion % / yards-per-catch etc. are correctly volume-weighted):
  QB:        CMP%, YDS/ATT, Pass YDS, Pass TD, INT, Sacks, YPG
  Rushing:   YPC (yards/carry), Rush YDS, Rush TD, YPG
  Receiving: Catch%, YPC (yards/catch), Rec YDS, Rec TD, YPG

No composite "+"-style rating (like the basketball tracker's Nick+) is
computed here — there's no similarly well-established single-number
box-score formula for football the way Hollinger's Game Score is for
basketball, so leaderboards sort by raw yardage/efficiency instead.

Data is stored per-player per-game so season/team/league filters can be
applied in memory without re-fetching from ESPN.
"""
from __future__ import annotations

import espn_nfl
import espn_cfb
import nfl_dates

_LEAGUE_MODULES = {"nfl": espn_nfl, "college": espn_cfb}
_LEAGUE_DISPLAY = {"nfl": "NFL", "college": "College"}
_CATEGORIES = ("qb", "rushing", "receiving")
_CATEGORY_TO_BOXSCORE_KEY = {"qb": "passing", "rushing": "rushing", "receiving": "receiving"}


# ── Data collection ───────────────────────────────────────────────────────────

def collect_player_game_stats(watched: dict) -> dict:
    """
    Fetch box score data for every watched game (NFL or college, per each
    game's "league" tag) and split into three per-player, per-game pools:

      {"qb": {name: {"athlete_id":..., "games":[...]}, ...},
       "rushing": {...},
       "receiving": {...}}

    Each game record in a pool has: game_id, season, team, league, plus
    that pool's own stat keys (see espn_nfl._parse_*_row for the exact
    fields per category).
    """
    pools = {cat: {} for cat in _CATEGORIES}

    game_ids = list(watched.keys())
    total    = len(game_ids)

    for i, gid in enumerate(game_ids, 1):
        game   = watched[gid]
        league = game.get("league", "nfl")
        module = _LEAGUE_MODULES.get(league, espn_nfl)
        season = nfl_dates.season_label(game["date"])
        icon   = "🎓" if league == "college" else "🏈"
        print(f"  Fetching game {i}/{total}: {icon} {game['date']}  {game['away']} @ {game['home']}...")
        try:
            data = module.fetch_boxscore_data(game["game_id"])
        except RuntimeError as e:
            print(f"    Warning: {e} — skipping.")
            continue

        for side in ("away", "home"):
            team_name = game["away"] if side == "away" else game["home"]
            side_data = data.get(side, {})

            for category in _CATEGORIES:
                box_key = _CATEGORY_TO_BOXSCORE_KEY[category]
                for athlete_id, p in side_data.get(box_key, {}).items():
                    name = p.get("name", athlete_id)
                    s    = p.get("stats", {})
                    pool = pools[category]
                    pool.setdefault(name, {"athlete_id": athlete_id, "games": []})
                    record = {"game_id": gid, "season": season, "team": team_name, "league": league}
                    record.update(s)
                    pool[name]["games"].append(record)

    return pools


# ── In-memory filtering & aggregation ────────────────────────────────────────

_COUNTING_KEYS = {
    "qb":        ["cmp", "att", "pass_yds", "pass_td", "int", "sacks", "sack_yds"],
    "rushing":   ["car", "rush_yds", "rush_td"],
    "receiving": ["rec", "rec_yds", "rec_td", "tgts"],
}


def _aggregate(category: str, games: list[dict]) -> dict:
    keys = _COUNTING_KEYS[category]
    acc = {k: 0 for k in keys}
    acc["appearances"] = 0
    acc["teams"] = {}
    acc["leagues"] = {}
    for g in games:
        for k in keys:
            acc[k] += g.get(k, 0)
        acc["appearances"] += 1
        acc["teams"][g["team"]] = acc["teams"].get(g["team"], 0) + 1
        league = g.get("league", "nfl")
        acc["leagues"][league] = acc["leagues"].get(league, 0) + 1
    return acc


def _primary_team(teams_dict: dict) -> str:
    if not teams_dict:
        return "—"
    return max(teams_dict, key=teams_dict.get)


def _primary_league(leagues_dict: dict) -> str:
    if not leagues_dict:
        return "nfl"
    return max(leagues_dict, key=leagues_dict.get)


def filter_and_aggregate(
    pool: dict,
    season_filter: str | None = None,
    team_filter:   str | None = None,
    league_filter: str | None = None,
    category: str = "qb",
) -> dict:
    """Apply season/team/league filters in memory. Returns an aggregated
    dict keyed by player name, in the shape calc_*_stats() expects."""
    def keep(g: dict) -> bool:
        if season_filter and g["season"] != season_filter:
            return False
        if team_filter and g["team"] != team_filter:
            return False
        if league_filter and g.get("league", "nfl") != league_filter:
            return False
        return True

    out: dict[str, dict] = {}
    for name, data in pool.items():
        matching = [g for g in data["games"] if keep(g)]
        if matching:
            agg = _aggregate(category, matching)
            agg["athlete_id"] = data.get("athlete_id")
            out[name] = agg

    return out


# ── Fantasy points ────────────────────────────────────────────────────────────
#
# Standard PPR (points-per-reception) scoring — the most common default
# across ESPN/Yahoo/Sleeper leagues:
#   Passing:   1 pt / 25 yds,  4 pts / TD,  -2 pts / INT
#   Rushing:   1 pt / 10 yds,  6 pts / TD
#   Receiving: 1 pt / 10 yds,  6 pts / TD,  1 pt / reception
#
# Scored PER CATEGORY, matching how each leaderboard is scoped — the QB
# table's fantasy points are passing points only, Rushing's are rushing
# points only, and so on. A real fantasy score for a dual-threat player
# (say, a rushing QB) would sum passing + rushing together, but each
# leaderboard here only has that one category's box score line for a given
# player, so combining across categories isn't done. Fumbles aren't
# tracked by this project at all (see espn_nfl.py's tracked-categories
# note), so fumble-lost penalties aren't reflected here either.

def _passing_fantasy_pts(pass_yds: int, pass_td: int, ints: int) -> float:
    return pass_yds / 25 + pass_td * 4 - ints * 2


def _rushing_fantasy_pts(rush_yds: int, rush_td: int) -> float:
    return rush_yds / 10 + rush_td * 6


def _receiving_fantasy_pts(rec_yds: int, rec_td: int, rec: int) -> float:
    return rec_yds / 10 + rec_td * 6 + rec * 1


# ── Stat calculators ────────────────────────────────────────────────────────

def calc_qb_stats(name: str, raw: dict) -> dict | None:
    app = raw["appearances"]
    if app == 0 or raw["att"] == 0:
        return None

    cmp_pct  = raw["cmp"] / raw["att"]
    ypa      = raw["pass_yds"] / raw["att"]
    ypg      = raw["pass_yds"] / app
    rating   = _passer_rating(raw["cmp"], raw["att"], raw["pass_yds"], raw["pass_td"], raw["int"])
    fpts     = _passing_fantasy_pts(raw["pass_yds"], raw["pass_td"], raw["int"])
    fppg     = fpts / app

    return {
        "name": name, "athlete_id": raw.get("athlete_id"),
        "team": _primary_team(raw.get("teams", {})),
        "league": _primary_league(raw.get("leagues", {})),
        "app": app,
        "cmp": raw["cmp"], "att": raw["att"],
        "_cmp_pct": cmp_pct, "cmp_pct": f"{cmp_pct*100:.1f}",
        "_ypa": ypa, "ypa": f"{ypa:.1f}",
        "pass_yds": raw["pass_yds"],
        "_ypg": ypg, "ypg": f"{ypg:.1f}",
        "pass_td": raw["pass_td"],
        "int": raw["int"],
        "sacks": raw["sacks"], "sack_yds": raw["sack_yds"],
        "_rating": rating, "rating": f"{rating:.1f}",
        "_fppg": fppg, "fppg": f"{fppg:.1f}",
    }


def calc_rushing_stats(name: str, raw: dict) -> dict | None:
    app = raw["appearances"]
    if app == 0 or raw["car"] == 0:
        return None

    ypc = raw["rush_yds"] / raw["car"]
    ypg = raw["rush_yds"] / app
    rush_val = _rush_value_per_carry(raw["rush_yds"], raw["rush_td"], raw["car"])
    fpts = _rushing_fantasy_pts(raw["rush_yds"], raw["rush_td"])
    fppg = fpts / app

    return {
        "name": name, "athlete_id": raw.get("athlete_id"),
        "team": _primary_team(raw.get("teams", {})),
        "league": _primary_league(raw.get("leagues", {})),
        "app": app,
        "car": raw["car"],
        "rush_yds": raw["rush_yds"],
        "_ypc": ypc, "ypc": f"{ypc:.1f}",
        "_ypg": ypg, "ypg": f"{ypg:.1f}",
        "rush_td": raw["rush_td"],
        "_rush_val": rush_val,
        "_fppg": fppg, "fppg": f"{fppg:.1f}",
    }


def calc_receiving_stats(name: str, raw: dict) -> dict | None:
    app = raw["appearances"]
    if app == 0 or raw["rec"] == 0:
        return None

    ypc = raw["rec_yds"] / raw["rec"] if raw["rec"] else 0.0
    ypg = raw["rec_yds"] / app
    catch_pct = raw["rec"] / raw["tgts"] if raw["tgts"] else None
    rec_val = _rec_value_per_target(raw["rec_yds"], raw["rec_td"], raw["tgts"], raw["rec"])
    fpts = _receiving_fantasy_pts(raw["rec_yds"], raw["rec_td"], raw["rec"])
    fppg = fpts / app

    return {
        "name": name, "athlete_id": raw.get("athlete_id"),
        "team": _primary_team(raw.get("teams", {})),
        "league": _primary_league(raw.get("leagues", {})),
        "app": app,
        "rec": raw["rec"], "tgts": raw["tgts"],
        "_catch_pct": catch_pct if catch_pct is not None else 0.0,
        "catch_pct": f"{catch_pct*100:.1f}" if catch_pct is not None else "—",
        "rec_yds": raw["rec_yds"],
        "_ypc": ypc, "ypc": f"{ypc:.1f}",
        "_ypg": ypg, "ypg": f"{ypg:.1f}",
        "rec_td": raw["rec_td"],
        "_rec_val": rec_val,
        "_fppg": fppg, "fppg": f"{fppg:.1f}",
    }


_CALCULATORS = {
    "qb": calc_qb_stats,
    "rushing": calc_rushing_stats,
    "receiving": calc_receiving_stats,
}


# ── Composite "+" ratings ────────────────────────────────────────────────────
#
# Same idea as the basketball tracker's Nick+: 100 = average of the
# comparison pool, higher is always better, shrunk toward the pool average
# based on sample size so a small-sample outlier doesn't look like a star.
#
# QB+ is built on NFL passer rating — the standard, public, non-proprietary
# formula the league itself uses (0-158.3 scale), computed here from
# AGGREGATED totals rather than averaging each game's reported rating,
# which is the statistically correct way to combine it across games.
#
# Rush+ and Rec+ do NOT have an equivalent well-established single-number
# public formula the way passer rating or Hollinger's Game Score do, so
# these are our own straightforward construction: yards per opportunity
# (carry / target) with a flat bonus per touchdown, on the reasoning that
# a broken-off long touchdown from a normal-looking carry should count for
# more than the yardage line alone shows. Treat Rush+/Rec+ as directional,
# not authoritative, the way you'd treat any homemade stat.

def _passer_rating(cmp_: int, att: int, yds: int, td: int, ints: int) -> float:
    """Standard NFL passer rating formula, each of the four components
    clamped to [0, 2.375] per the official spec."""
    if att == 0:
        return 0.0
    a = max(0.0, min(2.375, ((cmp_ / att) - 0.3) * 5))
    b = max(0.0, min(2.375, ((yds / att) - 3) * 0.25))
    c = max(0.0, min(2.375, (td / att) * 20))
    d = max(0.0, min(2.375, 2.375 - (ints / att * 25)))
    return (a + b + c + d) / 6 * 100


_TD_BONUS_YDS = 20   # flat yardage-equivalent credit per touchdown in Rush+/Rec+


def _rush_value_per_carry(rush_yds: int, rush_td: int, car: int) -> float:
    if car == 0:
        return 0.0
    return (rush_yds + _TD_BONUS_YDS * rush_td) / car


def _rec_value_per_target(rec_yds: int, rec_td: int, tgts: int, rec: int) -> float:
    denom = tgts if tgts > 0 else rec   # fall back to per-reception if targets weren't reported
    if denom == 0:
        return 0.0
    return (rec_yds + _TD_BONUS_YDS * rec_td) / denom


_VALUE_KEY = {"qb": "_rating", "rushing": "_rush_val", "receiving": "_rec_val"}
_PLUS_LABEL = {"qb": "QB+", "rushing": "Rush+", "receiving": "Rec+"}
_K_CREDIBILITY = {"qb": 100.0, "rushing": 60.0, "receiving": 40.0}   # volume for 50% credibility


def _plus_volume(category: str, row: dict) -> float:
    """The 'sample size' used for shrinkage credibility — attempts for QB,
    carries for rushing, and targets-or-receptions for receiving (falls
    back to receptions if targets weren't reported that game)."""
    if category == "qb":
        return row.get("att", 0)
    if category == "rushing":
        return row.get("car", 0)
    return row.get("tgts", 0) or row.get("rec", 0)


def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    total_w = sum(w for _, w in pairs if w > 0)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in pairs if w > 0) / total_w


def compute_pool_baseline(category: str, pool_rows: list[dict]) -> dict | None:
    """Volume-weighted average of the category's underlying value stat
    across a pool of player rows. None if the pool is empty/degenerate."""
    value_key = _VALUE_KEY[category]
    avg = _weighted_mean([(r[value_key], _plus_volume(category, r)) for r in pool_rows])
    if avg is None:
        return None
    return {"value": avg}


def plus_score(category: str, row: dict, baseline: dict | None) -> int | None:
    """The '+' score for one player row. None if there's no usable baseline
    or the player has no volume in this category."""
    if not baseline or baseline["value"] is None or baseline["value"] <= 0:
        return None
    volume = _plus_volume(category, row)
    if volume <= 0:
        return None
    k = _K_CREDIBILITY[category]
    credibility = volume / (volume + k)
    value_key = _VALUE_KEY[category]
    shrunk = credibility * row[value_key] + (1 - credibility) * baseline["value"]
    return round(100 * shrunk / baseline["value"])


def annotate_plus(rows: list[dict], category: str, pool_rows: list[dict] | None = None) -> list[dict]:
    """Attach 'plus' (int|None) and 'plus_disp' (display string) to each row
    in place. pool_rows defaults to `rows` itself; pass a separate pool when
    scoring rows that aren't the comparison set (e.g. one player's season
    lines vs. everyone you've watched in that category)."""
    baseline = compute_pool_baseline(category, pool_rows if pool_rows is not None else rows)
    for r in rows:
        p = plus_score(category, r, baseline)
        r["plus"] = p
        r["plus_disp"] = str(p) if p is not None else "—"
    return rows


# ── Leaderboard ────────────────────────────────────────────────────────────────

_MIN_DEFAULTS = {"qb": 5, "rushing": 5, "receiving": 3}   # min attempts/carries/receptions to qualify
_MIN_KEY = {"qb": "att", "rushing": "car", "receiving": "rec"}


def player_leaderboard(pool_raw: dict, category: str, min_volume: float | None = None) -> list[dict]:
    """Return qualifying players with computed stats for one category. No sort applied.
    min_volume: overrides the category's default minimum volume (attempts/carries/receptions)."""
    threshold = min_volume if min_volume is not None else _MIN_DEFAULTS[category]
    key = _MIN_KEY[category]
    calc = _CALCULATORS[category]
    rows = []
    for name, raw in pool_raw.items():
        if raw.get(key, 0) < threshold:
            continue
        row = calc(name, raw)
        if row:
            rows.append(row)
    return rows


# ── Per-player season breakdown (for the Search Player screen) ───────────────

def _group_by_season_team_league(games: list[dict]) -> dict[tuple[str, str, str], list[dict]]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for g in games:
        key = (g["season"], g["team"], g.get("league", "nfl"))
        groups.setdefault(key, []).append(g)
    return groups


def player_season_rows(name: str, games: list[dict], category: str) -> list[dict]:
    """
    One row per (season, team, league) for this player in this stat
    category, oldest to newest. If a player has games in more than one
    league, per-league subtotal rows are added, followed by a grand
    "ALL (Career)" row — same pattern as the basketball tracker's combined
    career view, so a QB's college passing days count toward their overall
    aggregate alongside their NFL days.
    """
    calc = _CALCULATORS[category]
    groups = _group_by_season_team_league(games)
    rows = []
    for season, team, league in sorted(groups):
        agg = _aggregate(category, groups[(season, team, league)])
        row = calc(name, agg)
        if row:
            row["season"] = season
            rows.append(row)

    leagues_present = {league for _, _, league in groups}

    if len(leagues_present) > 1:
        for league in ("college", "nfl"):
            if league not in leagues_present:
                continue
            league_games = [g for g in games if g.get("league", "nfl") == league]
            agg = _aggregate(category, league_games)
            row = calc(name, agg)
            if row:
                row["season"] = f"ALL ({_LEAGUE_DISPLAY[league]})"
                row["team"] = "ALL"
                rows.append(row)

    if len(groups) > 1:
        total_agg = _aggregate(category, games)
        total_row = calc(name, total_agg)
        if total_row:
            total_row["season"] = "ALL (Career)"
            total_row["team"] = "ALL"
            total_row["league"] = "ALL"
            rows.append(total_row)

    return rows
