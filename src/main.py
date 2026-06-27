#!/usr/bin/env python3
"""
main.py
MLB Watched Games Tracker — entry point.
All UI screens and the main menu loop live here.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

import mlb
import player_summary
import json_store


# ── Display helpers ───────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  ⚾  {title}")
    print("=" * 60)


def game_label(game: dict) -> str:
    """Format a schedule game dict as a single readable line."""
    away       = game["away_name"]
    home       = game["home_name"]
    date       = game["game_date"]
    away_score = game.get("away_score", "")
    home_score = game.get("home_score", "")
    status     = game.get("status", "")

    if away_score != "" and home_score != "":
        score = f"  ({away_score}–{home_score})"
    else:
        score = f"  [{status}]"

    return f"{date}  {away} @ {home}{score}"


# ── Screen: Browse Season ─────────────────────────────────────────────────────

def browse_season(watched: dict):
    """Pick a team + season, then page through games to mark as watched."""
    print_header("Browse Season")

    team_query = input("\nEnter team name (e.g. Braves, Yankees): ").strip()
    if not team_query:
        return

    results = mlb.find_teams(team_query)
    if not results:
        print("No team found. Try a different name.")
        input("\nPress Enter to continue...")
        return

    if len(results) > 1:
        print("\nMultiple teams found:")
        for i, t in enumerate(results):
            print(f"  [{i+1}] {t['name']}  (id: {t['id']})")
        choice = input("Select number: ").strip()
        try:
            team = results[int(choice) - 1]
        except (ValueError, IndexError):
            print("Invalid choice.")
            input("\nPress Enter to continue...")
            return
    else:
        team = results[0]

    season = input("\nEnter season year (e.g. 2014): ").strip()
    if not season.isdigit():
        print("Invalid year.")
        input("\nPress Enter to continue...")
        return

    print(f"\nFetching {team['name']} {season} schedule...")
    try:
        games = mlb.fetch_season_schedule(team["id"], season)
    except RuntimeError as e:
        print(f"Error: {e}")
        input("\nPress Enter to continue...")
        return

    if not games:
        print("No regular season games found.")
        input("\nPress Enter to continue...")
        return

    _game_select_loop(games, watched, team["name"], season)


def _game_select_loop(games: list, watched: dict, team_name: str, season: str):
    """Paginated game list with toggle-to-watch."""
    page_size   = 15
    page        = 0
    total_pages = (len(games) - 1) // page_size + 1

    while True:
        clear()
        print_header(f"{team_name} — {season} Season")

        start = page * page_size
        chunk = games[start : start + page_size]

        print(f"\n  Page {page+1}/{total_pages}   ({len(games)} games total)\n")
        for i, game in enumerate(chunk):
            gid  = str(game["game_id"])
            star = "★" if gid in watched else " "
            print(f"  [{i+1:>2}] {star}  {game_label(game)}")

        print("\n" + "-" * 60)
        print("  Enter a game number to toggle watched  |  n=next  p=prev  q=quit")
        cmd = input("\n> ").strip().lower()

        if cmd == "q":
            break
        elif cmd == "n":
            if page < total_pages - 1:
                page += 1
        elif cmd == "p":
            if page > 0:
                page -= 1
        elif cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(chunk):
                game = chunk[idx]
                gid  = str(game["game_id"])
                if gid in watched:
                    del watched[gid]
                    print(f"\n  ✗ Removed: {game_label(game)}")
                else:
                    watched[gid] = {
                        "game_id":    game["game_id"],
                        "date":       game["game_date"],
                        "away":       game["away_name"],
                        "home":       game["home_name"],
                        "away_score": game.get("away_score", ""),
                        "home_score": game.get("home_score", ""),
                        "added_at":   datetime.now().isoformat(),
                    }
                    print(f"\n  ★ Added:   {game_label(game)}")
                json_store.save_watched(watched)
                input("  Press Enter to continue...")


# ── Screen: View Watched ──────────────────────────────────────────────────────

def view_watched(watched: dict):
    """List all watched games, grouped by year."""
    clear()
    print_header("My Watched Games")

    if not watched:
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    by_year: dict[str, list] = {}
    for g in watched.values():
        year = g["date"][:4]
        by_year.setdefault(year, []).append(g)

    total = len(watched)
    print(f"\n  {total} game{'s' if total != 1 else ''} watched\n")

    for year in sorted(by_year.keys(), reverse=True):
        games = sorted(by_year[year], key=lambda g: g["date"])
        print(f"  ── {year} ({len(games)} games) ──")
        for g in games:
            away_s = g.get("away_score", "")
            home_s = g.get("home_score", "")
            score  = f"  {away_s}–{home_s}" if away_s != "" else ""
            print(f"    {g['date']}  {g['away']} @ {g['home']}{score}")
        print()

    input("Press Enter to continue...")


# ── Screen: Remove Watched ────────────────────────────────────────────────────

def remove_watched(watched: dict):
    """Remove a single game from the watched list."""
    clear()
    print_header("Remove a Watched Game")

    if not watched:
        print("\n  Nothing to remove.")
        input("\nPress Enter to continue...")
        return

    games = sorted(watched.values(), key=lambda g: g["date"])
    for i, g in enumerate(games):
        away_s = g.get("away_score", "")
        home_s = g.get("home_score", "")
        score  = f"  {away_s}–{home_s}" if away_s != "" else ""
        print(f"  [{i+1:>2}]  {g['date']}  {g['away']} @ {g['home']}{score}")

    print("\n  Enter number to remove, or q to cancel.")
    cmd = input("\n> ").strip().lower()

    if cmd == "q":
        return
    if cmd.isdigit():
        idx = int(cmd) - 1
        if 0 <= idx < len(games):
            g   = games[idx]
            gid = str(g["game_id"])
            del watched[gid]
            json_store.save_watched(watched)
            print(f"\n  Removed: {g['date']}  {g['away']} @ {g['home']}")
    input("\nPress Enter to continue...")


# ── Filter helpers ────────────────────────────────────────────────────────────

def _all_seasons(watched: dict) -> list[str]:
    return sorted({g["date"][:4] for g in watched.values()})


def _all_teams(watched: dict) -> list[str]:
    teams = set()
    for g in watched.values():
        teams.add(g["away"])
        teams.add(g["home"])
    return sorted(teams)


def _apply_watched_filters(
    watched: dict,
    season_filter: str | None,
    team_filter: str | None,
) -> dict:
    """Return a subset of watched matching the active season and/or team filters."""
    out = {}
    for gid, g in watched.items():
        if season_filter and g["date"][:4] != season_filter:
            continue
        if team_filter and team_filter not in (g["away"], g["home"]):
            continue
        out[gid] = g
    return out


def _filters_label(
    season_filter: str | None,
    team_filter: str | None,
    ip_min: float | None,
) -> str:
    parts = []
    if season_filter:
        parts.append(f"season={season_filter}")
    if team_filter:
        parts.append(f"team={team_filter}")
    if ip_min is not None:
        parts.append(f"IP≥{ip_min:.1f}")
    return "  |  filters: " + ", ".join(parts) if parts else ""


def _filter_prompt(
    watched: dict,
    season_filter: str | None,
    team_filter: str | None,
    ip_min: float | None,
    show_ip: bool = False,
) -> tuple[str | None, str | None, float | None] | None:
    """
    Interactive filter menu.
    Returns (season_filter, team_filter, ip_min) with updated values,
    or None if the user pressed q (meaning go back without changes).
    """
    seasons = _all_seasons(watched)
    teams   = _all_teams(watched)

    while True:
        print("\n  ── Active filters ──────────────────────────────")
        print(f"    Season : {season_filter or 'all'}")
        print(f"    Team   : {team_filter   or 'all'}")
        if show_ip:
            print(f"    Min IP : {ip_min:.1f}" if ip_min is not None else "    Min IP : none")

        print("\n  ── Change filter ───────────────────────────────")
        print("    [1] Season")
        print("    [2] Team")
        if show_ip:
            print("    [3] Min IP (pitchers only)")
        print("    [x] Clear all filters")
        print("    [q] Done")
        cmd = input("\n  > ").strip().lower()

        if cmd == "q":
            return season_filter, team_filter, ip_min

        elif cmd == "x":
            season_filter, team_filter, ip_min = None, None, None
            print("  Filters cleared.")

        elif cmd == "1":
            if not seasons:
                print("  No seasons available.")
                continue
            print("\n  Available seasons:")
            print("    [0] All seasons")
            for i, s in enumerate(seasons, 1):
                marker = " ◀" if s == season_filter else ""
                print(f"    [{i}] {s}{marker}")
            pick = input("  > ").strip()
            if pick == "0":
                season_filter = None
            elif pick.isdigit():
                idx = int(pick) - 1
                if 0 <= idx < len(seasons):
                    season_filter = seasons[idx]

        elif cmd == "2":
            if not teams:
                print("  No teams available.")
                continue
            print("\n  Available teams:")
            print("    [0] All teams")
            for i, t in enumerate(teams, 1):
                marker = " ◀" if t == team_filter else ""
                print(f"    [{i}] {t}{marker}")
            pick = input("  > ").strip()
            if pick == "0":
                team_filter = None
            elif pick.isdigit():
                idx = int(pick) - 1
                if 0 <= idx < len(teams):
                    team_filter = teams[idx]

        elif cmd == "3" and show_ip:
            raw = input("  Minimum IP (e.g. 5.0), or 0 to clear: ").strip()
            try:
                val = float(raw)
                ip_min = None if val == 0 else val
            except ValueError:
                print("  Invalid number.")


# ── Sort / limit helpers ──────────────────────────────────────────────────────

def _sort_prompt(cols: list[tuple[str, str, bool]]) -> tuple[str, bool] | None:
    """
    Display the action menu and return one of:
      (sort_key, reverse)           — user picked a sort column
      "csv"                         — export to CSV
      ("limit", "h"|"t")           — change head/tail limit
      "filter"                      — open filter menu
      None                          — go back
      False                         — invalid input (re-prompt)
    """
    print("\n  Sort by:")
    for i, (label, _, _) in enumerate(cols, 1):
        print(f"    [{i}] {label}")
    print("    [h] Show top N (head)")
    print("    [t] Show bottom N (tail)")
    print("    [f] Filters")
    print("    [c] Export to CSV")
    print("    [q] Back")
    cmd = input("\n  > ").strip().lower()
    if cmd == "q":
        return None
    if cmd == "c":
        return "csv"
    if cmd == "f":
        return "filter"
    if cmd in ("h", "t"):
        return ("limit", cmd)
    if cmd.isdigit():
        idx = int(cmd) - 1
        if 0 <= idx < len(cols):
            _, key, rev = cols[idx]
            return key, rev
    return False


def _ask_limit(current_limit: int | None, current_tail: bool) -> tuple[int | None, bool]:
    direction = "tail" if current_tail else "head"
    showing   = f"{current_limit} ({direction})" if current_limit else "all"
    print(f"\n  Currently showing: {showing}")
    print("  Enter a number to limit rows, or 0 to show all.")
    raw = input("  Rows: ").strip()
    if not raw.isdigit():
        return current_limit, current_tail
    n = int(raw)
    if n == 0:
        return None, current_tail
    return n, current_tail


def _apply_limit(rows: list, limit: int | None, from_tail: bool) -> list:
    if limit is None:
        return rows
    return rows[-limit:] if from_tail else rows[:limit]


def _limit_label(limit: int | None, from_tail: bool) -> str:
    if limit is None:
        return "all rows"
    return f"bottom {limit}" if from_tail else f"top {limit}"


# ── CSV export helper ─────────────────────────────────────────────────────────

def _dump_csv(filename: str, headers: list[str], rows: list[dict], display_keys: list[str]) -> None:
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([r[k] for k in display_keys])
    print(f"\n  ✓ Exported {len(rows)} rows to {filename}")
    input("  Press Enter to continue...")


# ── Screen: Game Summary ──────────────────────────────────────────────────────

_GAME_SORT_COLS = [
    ("Team name",    "name", False),
    ("Wins",         "W",    True),
    ("Losses",       "L",    False),
    ("Win %",        "pct",  True),
    ("Runs scored",  "rs",   True),
    ("Runs allowed", "ra",   False),
    ("Games",        "g",    True),
    ("Runs/game",    "rpg",  True),
]


def summary(watched: dict):
    """Show per-team record and run stats across all watched games."""
    if not watched:
        clear()
        print_header("Game Summary")
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    # Filter state (season + team only; no IP for game summary)
    season_filter: str | None = None
    team_filter:   str | None = None

    sort_col, sort_rev  = "pct", True
    limit, from_tail    = 25, False

    while True:
        active = _apply_watched_filters(watched, season_filter, team_filter)
        scored = [
            g for g in active.values()
            if g.get("away_score", "") != "" and g.get("home_score", "") != ""
        ]

        # Build per-team rows
        teams: dict[str, dict] = {}
        def get_team(name):
            if name not in teams:
                teams[name] = {"W": 0, "L": 0, "rs": 0, "ra": 0, "g": 0}
            return teams[name]

        for g in scored:
            a = int(g["away_score"]); h = int(g["home_score"])
            at = get_team(g["away"]); ht = get_team(g["home"])
            at["g"] += 1; at["rs"] += a; at["ra"] += h
            ht["g"] += 1; ht["rs"] += h; ht["ra"] += a
            if a > h:   at["W"] += 1; ht["L"] += 1
            elif h > a: ht["W"] += 1; at["L"] += 1

        rows = []
        for name, t in teams.items():
            total = t["W"] + t["L"]
            pct   = t["W"] / total if total else 0
            rpg   = t["rs"] / t["g"] if t["g"] else 0
            rows.append({
                "name": name, "W": t["W"], "L": t["L"],
                "pct": pct, "rs": t["rs"], "ra": t["ra"],
                "g": t["g"], "rpg": rpg,
            })

        rows.sort(
            key=lambda r: r[sort_col] if isinstance(r[sort_col], (int, float)) else r[sort_col].lower(),
            reverse=sort_rev,
        )
        visible = _apply_limit(rows, limit, from_tail)

        clear()
        print_header("Game Summary")
        sort_label = next(l for l, k, _ in _GAME_SORT_COLS if k == sort_col)
        fl = _filters_label(season_filter, team_filter, None)
        print(f"\n  {len(scored)} game(s)  |  {len(teams)} teams  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}{fl}\n")

        if not scored:
            print("  No completed games match current filters.")
        else:
            total_runs = sum(int(g["away_score"]) + int(g["home_score"]) for g in scored)
            avg_runs   = total_runs / len(scored)
            highest = max(scored, key=lambda g: int(g["away_score"]) + int(g["home_score"]))
            lowest  = min(scored, key=lambda g: int(g["away_score"]) + int(g["home_score"]))
            blowout = max(scored, key=lambda g: abs(int(g["away_score"]) - int(g["home_score"])))
            margin  = abs(int(blowout["away_score"]) - int(blowout["home_score"]))

            col = "{:<26}  {:>3}  {:>3}  {:>5}  {:>6}  {:>6}  {:>5}  {:>6}"
            print(col.format("Team", "W", "L", "PCT", "RS", "RA", "G", "R/G"))
            print("  " + "-" * 58)
            for r in visible:
                print("  " + col.format(
                    r["name"][:26], r["W"], r["L"],
                    f"{r['pct']:.3f}", r["rs"], r["ra"],
                    r["g"], f"{r['rpg']:.1f}",
                ))

            print("\n" + "-" * 60)
            print(f"  Avg runs/game: {avg_runs:.1f}")
            print(f"  🔥 Highest-scoring: {highest['date']}  {highest['away']} @ {highest['home']}  ({highest['away_score']}–{highest['home_score']})")
            print(f"  🥱 Lowest-scoring:  {lowest['date']}  {lowest['away']} @ {lowest['home']}  ({lowest['away_score']}–{lowest['home_score']})")
            print(f"  💥 Biggest blowout: {blowout['date']}  {blowout['away']} @ {blowout['home']}  ({blowout['away_score']}–{blowout['home_score']}, margin: {margin})")

        result = _sort_prompt(_GAME_SORT_COLS)
        if result is None:
            return
        if result == "csv":
            csv_rows = [{**r, "pct": f"{r['pct']:.3f}", "rpg": f"{r['rpg']:.1f}"} for r in visible]
            _dump_csv(
                "game_summary.csv",
                ["Team", "W", "L", "PCT", "RS", "RA", "G", "R/G"],
                csv_rows,
                ["name", "W", "L", "pct", "rs", "ra", "g", "rpg"],
            )
            continue
        if result == "filter":
            season_filter, team_filter, _ = _filter_prompt(
                watched, season_filter, team_filter, None, show_ip=False
            )
            continue
        if isinstance(result, tuple) and result[0] == "limit":
            limit, from_tail = _ask_limit(limit, result[1] == "t")
            continue
        if result is False:
            continue
        sort_col, sort_rev = result


# ── Screen: Player Summary ────────────────────────────────────────────────────

def screen_player_summary(watched: dict):
    """Sub-menu: choose pitchers or batters."""
    if not watched:
        clear()
        print_header("Player Summary")
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    while True:
        clear()
        print_header("Player Summary")
        print(f"\n  Stats aggregated across {len(watched)} watched game(s).\n")
        print("  [1]  Pitchers")
        print("  [2]  Batters")
        print("  [q]  Back\n")
        cmd = input("> ").strip().lower()
        if cmd == "q":
            return
        elif cmd == "1":
            _show_pitching(watched)
        elif cmd == "2":
            _show_batting(watched)


_PITCH_SORT_COLS = [
    ("Name",        "name",  False),
    ("Team",        "team",  False),
    ("Appearances", "app",   True),
    ("IP",          "_outs", True),
    ("ERA",         "_era",  False),
    ("WHIP",        "_whip", False),
    ("K/9",         "_k9",   True),
    ("BB/9",        "_bb9",  False),
    ("HR/9",        "_hr9",  False),
]

_BAT_SORT_COLS = [
    ("Name",        "name",  False),
    ("Team",        "team",  False),
    ("Appearances", "app",   True),
    ("AB",          "ab",    True),
    ("AVG",         "_avg",  True),
    ("OBP",         "_obp",  True),
    ("SLG",         "_slg",  True),
    ("OPS",         "_ops",  True),
]


def _show_pitching(watched: dict):
    season_filter: str | None = None
    team_filter:   str | None = None
    ip_min:        float | None = None

    sort_col, sort_rev = "_era", False
    limit, from_tail   = 25, False

    # fetch once; re-filter in memory from here
    clear()
    print_header("Pitcher Summary")
    print(f"\n  Fetching boxscore data for {len(watched)} game(s)...\n")
    try:
        all_pitchers, _ = player_summary.collect_player_game_stats(watched)
    except Exception as e:
        print(f"\n  Error collecting stats: {e}")
        input("\nPress Enter to continue...")
        return

    from player_summary import ip_to_outs

    while True:
        # Apply season/team filter to the raw pitcher accumulations
        # We need to re-run collection if watched subset changes — but since
        # collect already keyed stats per player across all games, we filter
        # by re-running on the filtered watched subset only when filters change.
        # For simplicity and correctness, re-collect from filtered watched each loop.
        filtered_watched = _apply_watched_filters(watched, season_filter, team_filter)

        if (season_filter or team_filter) and filtered_watched != watched:
            pitchers, _ = player_summary.collect_player_game_stats(filtered_watched)
        else:
            pitchers = all_pitchers

        rows = player_summary.pitching_leaderboard(pitchers)
        for r in rows:
            r["_outs"] = ip_to_outs(r["ip"])

        # Apply IP minimum filter
        if ip_min is not None:
            rows = [r for r in rows if r["_outs"] >= ip_min * 3]

        sorted_rows = sorted(
            rows,
            key=lambda r: (r[sort_col] if isinstance(r[sort_col], (int, float))
                           else r[sort_col].lower()),
            reverse=sort_rev,
        )
        visible = _apply_limit(sorted_rows, limit, from_tail)

        clear()
        print_header("Pitcher Summary")
        sort_label = next(l for l, k, _ in _PITCH_SORT_COLS if k == sort_col)
        fl = _filters_label(season_filter, team_filter, ip_min)
        print(f"\n  {len(rows)} pitchers  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}{fl}\n")

        if not rows:
            print(f"  No pitchers match current filters (min {player_summary.MIN_PITCHER_OUTS} outs).")
        else:
            col = "{:<22}  {:<22}  {:>4}  {:>6}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}"
            print(col.format("Name", "Team", "App", "IP", "ERA", "WHIP", "K/9", "BB/9", "HR/9"))
            print("  " + "-" * 80)
            for r in visible:
                print("  " + col.format(
                    r["name"][:22], r["team"][:22],
                    r["app"], r["ip"],
                    r["era"], r["whip"], r["k9"], r["bb9"], r["hr9"],
                ))

        result = _sort_prompt(_PITCH_SORT_COLS)
        if result is None:
            return
        if result == "csv":
            _dump_csv(
                "pitcher_summary.csv",
                ["Name", "Team", "App", "IP", "ERA", "WHIP", "K/9", "BB/9", "HR/9"],
                visible,
                ["name", "team", "app", "ip", "era", "whip", "k9", "bb9", "hr9"],
            )
            continue
        if result == "filter":
            season_filter, team_filter, ip_min = _filter_prompt(
                watched, season_filter, team_filter, ip_min, show_ip=True
            )
            continue
        if isinstance(result, tuple) and result[0] == "limit":
            limit, from_tail = _ask_limit(limit, result[1] == "t")
            continue
        if result is False:
            continue
        sort_col, sort_rev = result


def _show_batting(watched: dict):
    season_filter: str | None = None
    team_filter:   str | None = None

    sort_col, sort_rev = "_ops", True
    limit, from_tail   = 25, False

    clear()
    print_header("Batter Summary")
    print(f"\n  Fetching boxscore data for {len(watched)} game(s)...\n")
    try:
        _, all_batters = player_summary.collect_player_game_stats(watched)
    except Exception as e:
        print(f"\n  Error collecting stats: {e}")
        input("\nPress Enter to continue...")
        return

    while True:
        filtered_watched = _apply_watched_filters(watched, season_filter, team_filter)

        if (season_filter or team_filter) and filtered_watched != watched:
            _, batters = player_summary.collect_player_game_stats(filtered_watched)
        else:
            batters = all_batters

        rows = player_summary.batting_leaderboard(batters)

        sorted_rows = sorted(
            rows,
            key=lambda r: (r[sort_col] if isinstance(r[sort_col], (int, float))
                           else r[sort_col].lower()),
            reverse=sort_rev,
        )
        visible = _apply_limit(sorted_rows, limit, from_tail)

        clear()
        print_header("Batter Summary")
        sort_label = next(l for l, k, _ in _BAT_SORT_COLS if k == sort_col)
        fl = _filters_label(season_filter, team_filter, None)
        print(f"\n  {len(rows)} batters  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}{fl}\n")

        if not rows:
            print(f"  No batters match current filters (min {player_summary.MIN_BATTER_AB} AB).")
        else:
            col = "{:<22}  {:<22}  {:>4}  {:>5}  {:>5}  {:>6}  {:>5}  {:>5}  {:>5}"
            print(col.format("Name", "Team", "App", "AB", "H", "AVG", "OBP", "SLG", "OPS"))
            print("  " + "-" * 80)
            for r in visible:
                print("  " + col.format(
                    r["name"][:22], r["team"][:22],
                    r["app"], r["ab"], r["h"],
                    r["avg"], r["obp"], r["slg"], r["ops"],
                ))

        result = _sort_prompt(_BAT_SORT_COLS)
        if result is None:
            return
        if result == "csv":
            _dump_csv(
                "batter_summary.csv",
                ["Name", "Team", "App", "AB", "H", "AVG", "OBP", "SLG", "OPS"],
                visible,
                ["name", "team", "app", "ab", "h", "avg", "obp", "slg", "ops"],
            )
            continue
        if result == "filter":
            season_filter, team_filter, _ = _filter_prompt(
                watched, season_filter, team_filter, None, show_ip=False
            )
            continue
        if isinstance(result, tuple) and result[0] == "limit":
            limit, from_tail = _ask_limit(limit, result[1] == "t")
            continue
        if result is False:
            continue
        sort_col, sort_rev = result


# ── Main menu ─────────────────────────────────────────────────────────────────

def main():
    while True:
        watched = json_store.load_watched()
        clear()
        print_header("MLB Watched Games Tracker")
        print(f"\n  Games watched: {len(watched)}")
        print(f"  Data file:     {json_store.watched_file_path()}\n")
        print("  [1]  Browse a season & mark games watched")
        print("  [2]  View all watched games")
        print("  [3]  Remove a watched game")
        print("  [4]  Game Summary")
        print("  [5]  Player Summary")
        print("  [q]  Quit\n")

        cmd = input("> ").strip().lower()

        if cmd == "1":
            browse_season(watched)
        elif cmd == "2":
            view_watched(watched)
        elif cmd == "3":
            remove_watched(watched)
        elif cmd == "4":
            summary(watched)
        elif cmd == "5":
            screen_player_summary(watched)
        elif cmd == "q":
            print("\nBye!\n")
            break


if __name__ == "__main__":
    main()
