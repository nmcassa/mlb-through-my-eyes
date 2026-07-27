"""
nba_player_summary.py
Aggregates per-player box score stats across a set of watched NBA games.

Counting stats collected per game: MIN, PTS, REB (+OREB/DREB), AST, STL,
BLK, TOV, PF, and made/attempted splits for FG, 3PT, FT.

Rate stats derived from the aggregated totals (not averaged per-game, so
shooting percentages are correctly weighted by volume):
  PPG, RPG, APG, SPG, BPG, MPG (simple per-game averages)
  FG%, 3P%, FT% (makes / attempts, summed across all watched games)

Also computes Nick+, a sample-size-aware composite similar to the MLB
tracker's Nick+: built on John Hollinger's Game Score (a well-known, public
box-score formula), normalized to a per-48-minutes rate (NOT a per-game
average — a raw per-game average inherently rewards players who simply play
more minutes, since counting stats accumulate the longer someone's on the
floor), then shrunk toward the pool average based on total minutes watched,
then scaled so 100 = average of the comparison pool. Higher is better.

Data is stored per-player per-game so season/team filters can be applied in
memory without re-fetching from ESPN.
"""
from __future__ import annotations

import espn_nba
import nba_dates


# ── Data collection ───────────────────────────────────────────────────────────

def collect_player_game_stats(watched: dict) -> dict:
    """
    Fetch box score data for every watched game and store per-player,
    per-game stats. Returns a dict keyed by player name:

      players[name] = {
          "athlete_id": ...,
          "games": [ { "game_id", "season", "team", "min", "pts", "reb",
                       "oreb", "dreb", "ast", "stl", "blk", "tov", "pf",
                       "fgm", "fga", "3pm", "3pa", "ftm", "fta" } ],
      }

    All filtering/aggregation happens downstream from these raw records, so
    no re-fetch is needed when the user changes season/team filters.
    """
    players: dict[str, dict] = {}

    game_ids = list(watched.keys())
    total    = len(game_ids)

    for i, gid in enumerate(game_ids, 1):
        game   = watched[gid]
        season = nba_dates.season_label(game["date"])
        print(f"  Fetching game {i}/{total}: {game['date']}  {game['away']} @ {game['home']}...")
        try:
            data = espn_nba.fetch_boxscore_data(game["game_id"])
        except RuntimeError as e:
            print(f"    Warning: {e} — skipping.")
            continue

        for side in ("away", "home"):
            team_name = game["away"] if side == "away" else game["home"]
            side_data = data.get(side, {})

            for athlete_id, p in side_data.get("players", {}).items():
                name = p.get("name", athlete_id)
                s    = p.get("stats", {})
                if s.get("min", 0) <= 0:
                    continue   # DNP — didn't actually play

                players.setdefault(name, {"athlete_id": athlete_id, "games": []})
                players[name]["games"].append({
                    "game_id": gid,
                    "season":  season,
                    "team":    team_name,
                    "min":  s.get("min", 0.0),
                    "pts":  s.get("pts", 0),
                    "reb":  s.get("reb", 0),
                    "oreb": s.get("oreb", 0),
                    "dreb": s.get("dreb", 0),
                    "ast":  s.get("ast", 0),
                    "stl":  s.get("stl", 0),
                    "blk":  s.get("blk", 0),
                    "tov":  s.get("tov", 0),
                    "pf":   s.get("pf", 0),
                    "fgm":  s.get("fgm", 0),
                    "fga":  s.get("fga", 0),
                    "3pm":  s.get("3pm", 0),
                    "3pa":  s.get("3pa", 0),
                    "ftm":  s.get("ftm", 0),
                    "fta":  s.get("fta", 0),
                })

    return players


# ── In-memory filtering & aggregation ────────────────────────────────────────

_COUNTING_KEYS = ["min", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk",
                   "tov", "pf", "fgm", "fga", "3pm", "3pa", "ftm", "fta"]


def _aggregate(games: list[dict]) -> dict:
    """Sum raw counting stats across a list of filtered game records."""
    acc = {k: 0 for k in _COUNTING_KEYS}
    acc["appearances"] = 0
    acc["teams"] = {}
    acc["game_scores"] = []   # per-game Game Score, kept for reference/debugging
    for g in games:
        for k in _COUNTING_KEYS:
            acc[k] += g.get(k, 0)
        acc["appearances"] += 1
        acc["teams"][g["team"]] = acc["teams"].get(g["team"], 0) + 1
        acc["game_scores"].append(_game_score(g))
    return acc


def _primary_team(teams_dict: dict) -> str:
    if not teams_dict:
        return "—"
    return max(teams_dict, key=teams_dict.get)


def filter_and_aggregate(
    players: dict,
    season_filter: str | None = None,
    team_filter:   str | None = None,
) -> dict:
    """
    Apply season and team filters entirely in memory — no API calls.

    season_filter: if set, only include game records from that year.
    team_filter:   if set, only include game records where the player's
                   team for that game matches.

    Returns an aggregated dict keyed by player name in the shape
    calc_player_stats() expects.
    """
    def keep(g: dict) -> bool:
        if season_filter and g["season"] != season_filter:
            return False
        if team_filter and g["team"] != team_filter:
            return False
        return True

    out: dict[str, dict] = {}
    for name, data in players.items():
        matching = [g for g in data["games"] if keep(g)]
        if matching:
            agg = _aggregate(matching)
            agg["athlete_id"] = data.get("athlete_id")
            out[name] = agg

    return out


# ── Game Score (Hollinger) ────────────────────────────────────────────────────

def _game_score(g: dict) -> float:
    """
    John Hollinger's Game Score — a well-known public formula that boils
    one box score line down to a single per-game number (roughly on a
    points-ish scale: ~10 = solid starter's night, ~40 = historic game).
    Used as the raw input to Nick+.
    """
    return (
        g.get("pts", 0)
        + 0.4 * g.get("fgm", 0)
        - 0.7 * g.get("fga", 0)
        - 0.4 * (g.get("fta", 0) - g.get("ftm", 0))
        + 0.7 * g.get("oreb", 0)
        + 0.3 * g.get("dreb", 0)
        + g.get("stl", 0)
        + 0.7 * g.get("ast", 0)
        + 0.7 * g.get("blk", 0)
        - 0.4 * g.get("pf", 0)
        - g.get("tov", 0)
    )


# ── Stat calculator ────────────────────────────────────────────────────────────

def calc_player_stats(name: str, raw: dict) -> dict:
    """Derive per-game averages and shooting splits from aggregated raw counting stats."""
    app = raw["appearances"]
    if app == 0:
        return None

    mpg = raw["min"] / app
    ppg = raw["pts"] / app
    rpg = raw["reb"] / app
    apg = raw["ast"] / app
    spg = raw["stl"] / app
    bpg = raw["blk"] / app
    topg = raw["tov"] / app

    fg_pct = raw["fgm"] / raw["fga"] if raw["fga"] else 0.0
    tp_pct = raw["3pm"] / raw["3pa"] if raw["3pa"] else 0.0
    ft_pct = raw["ftm"] / raw["fta"] if raw["fta"] else 0.0

    total_min = raw["min"]
    gmsc_sum  = sum(raw["game_scores"]) if raw["game_scores"] else 0.0
    gmsc_per48 = (gmsc_sum / total_min) * 48 if total_min > 0 else 0.0

    return {
        "name":       name,
        "athlete_id": raw.get("athlete_id"),
        "team":       _primary_team(raw.get("teams", {})),
        "app":        app,
        "min":        raw["min"],
        "_mpg": mpg,   "mpg": f"{mpg:.1f}",
        "_ppg": ppg,   "ppg": f"{ppg:.1f}",
        "_rpg": rpg,   "rpg": f"{rpg:.1f}",
        "_apg": apg,   "apg": f"{apg:.1f}",
        "_spg": spg,   "spg": f"{spg:.1f}",
        "_bpg": bpg,   "bpg": f"{bpg:.1f}",
        "_topg": topg, "topg": f"{topg:.1f}",
        "fgm": raw["fgm"], "fga": raw["fga"], "_fg_pct": fg_pct, "fg_pct": f"{fg_pct:.3f}",
        "3pm": raw["3pm"], "3pa": raw["3pa"], "_tp_pct": tp_pct, "tp_pct": f"{tp_pct:.3f}",
        "ftm": raw["ftm"], "fta": raw["fta"], "_ft_pct": ft_pct, "ft_pct": f"{ft_pct:.3f}",
        "_gmsc": gmsc_per48, "gmsc": f"{gmsc_per48:.1f}",
    }


# ── Leaderboard ────────────────────────────────────────────────────────────────

MIN_LEADERBOARD_MINUTES = 10   # at least ~1 real game's worth of minutes to appear


def player_leaderboard(players_raw: dict, min_min: float | None = None) -> list[dict]:
    """
    Return qualifying players with computed stats. No sort applied.
    min_min: optional minimum total minutes watched; overrides MIN_LEADERBOARD_MINUTES.
    """
    threshold = min_min if min_min is not None else MIN_LEADERBOARD_MINUTES
    rows = []
    for name, raw in players_raw.items():
        if raw["min"] < threshold:
            continue
        row = calc_player_stats(name, raw)
        if row:
            rows.append(row)
    return rows


# ── Per-player season breakdown (for the Search Player screen) ───────────────

def _group_by_season(games: list[dict]) -> dict[str, list[dict]]:
    seasons: dict[str, list[dict]] = {}
    for g in games:
        seasons.setdefault(g["season"], []).append(g)
    return seasons


def player_season_rows(name: str, games: list[dict]) -> list[dict]:
    """
    One row per season this player was watched, oldest to newest — only
    seasons with logged games appear. If more than one season is present, a
    trailing "ALL (logged)" row totals everything across all seasons.
    """
    seasons = _group_by_season(games)
    rows = []
    for season in sorted(seasons):
        agg = _aggregate(seasons[season])
        row = calc_player_stats(name, agg)
        if row:
            row["season"] = season
            rows.append(row)

    if len(seasons) > 1:
        total_agg = _aggregate(games)
        total_row = calc_player_stats(name, total_agg)
        if total_row:
            total_row["season"] = "ALL (logged)"
            rows.append(total_row)

    return rows


# ── Nick+ — a sample-size-aware normalized composite ──────────────────────────
#
# Same idea as the MLB tracker's Nick+: 100 = average of the comparison pool,
# higher is always better. Built on Game Score PER 48 MINUTES (see
# _game_score() above and the per48 conversion in calc_player_stats()) —
# using per-48 rather than a raw per-game average matters: a raw per-game
# average bakes in more minutes = more counting stats = a higher number,
# which would make Nick+ mostly measure playing time rather than quality.
# Per-48 is a true rate, so it doesn't automatically favor whoever's on the
# floor longer in a given game.
#
# On top of that rate, each player's number is shrunk toward the pool
# average based on TOTAL minutes watched across all their games — that part
# intentionally does still reward players you've watched more, since it's
# regression to the mean based on sample size, not raw production. A hot
# 15-minute cameo barely moves off 100; a guy you've watched heavy minutes
# across many games keeps most of his real per-48 rate.

_K_MIN = 200.0   # total minutes watched for 50% credibility (~5-6 starter games)


def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    total_w = sum(w for _, w in pairs if w > 0)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in pairs if w > 0) / total_w


def compute_pool_baseline(pool_rows: list[dict]) -> dict | None:
    """Minutes-weighted average Game Score/48 across a pool of player rows. None if empty."""
    gmsc_avg = _weighted_mean([(r["_gmsc"], r["min"]) for r in pool_rows])
    if gmsc_avg is None:
        return None
    return {"gmsc": gmsc_avg}


def nick_plus(row: dict, baseline: dict | None) -> int | None:
    """
    Nick+ for one player row. Shrinks their Game Score/48 toward the pool
    average based on total minutes watched, then scales so 100 = pool
    average. Returns None if there's no baseline or the pool average isn't
    usefully positive (a degenerate pool — shouldn't happen with real data).
    """
    minutes = row.get("min", 0)
    if not baseline or minutes <= 0 or baseline["gmsc"] <= 0:
        return None

    credibility  = minutes / (minutes + _K_MIN)
    shrunk_gmsc  = credibility * row["_gmsc"] + (1 - credibility) * baseline["gmsc"]
    return round(100 * shrunk_gmsc / baseline["gmsc"])


def annotate_nick_plus(rows: list[dict], pool_rows: list[dict] | None = None) -> list[dict]:
    """
    Attach 'nickplus' (int|None) and 'nick+' (display string) to each row
    in place. pool_rows defaults to `rows` itself; pass a separate pool when
    scoring rows that aren't the comparison set (e.g. one player's season
    lines vs. everyone you've watched).
    """
    baseline = compute_pool_baseline(pool_rows if pool_rows is not None else rows)
    for r in rows:
        n = nick_plus(r, baseline)
        r["nickplus"] = n
        r["nick+"] = str(n) if n is not None else "—"
    return rows
