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
    away = game["away_name"]
    home = game["home_name"]
    date = game["game_date"]
    away_score = game.get("away_score", "")
    home_score = game.get("home_score", "")
    status = game.get("status", "")

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
    page_size = 15
    page = 0
    total_pages = (len(games) - 1) // page_size + 1

    while True:
        clear()
        print_header(f"{team_name} — {season} Season")

        start = page * page_size
        chunk = games[start : start + page_size]

        print(f"\n  Page {page+1}/{total_pages}   ({len(games)} games total)\n")
        for i, game in enumerate(chunk):
            gid = str(game["game_id"])
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
                gid = str(game["game_id"])
                if gid in watched:
                    del watched[gid]
                    print(f"\n  ✗ Removed: {game_label(game)}")
                else:
                    watched[gid] = {
                        "game_id": game["game_id"],
                        "date": game["game_date"],
                        "away": game["away_name"],
                        "home": game["home_name"],
                        "away_score": game.get("away_score", ""),
                        "home_score": game.get("home_score", ""),
                        "added_at": datetime.now().isoformat(),
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
            score = f"  {away_s}–{home_s}" if away_s != "" else ""
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
        score = f"  {away_s}–{home_s}" if away_s != "" else ""
        print(f"  [{i+1:>2}]  {g['date']}  {g['away']} @ {g['home']}{score}")

    print("\n  Enter number to remove, or q to cancel.")
    cmd = input("\n> ").strip().lower()

    if cmd == "q":
        return
    if cmd.isdigit():
        idx = int(cmd) - 1
        if 0 <= idx < len(games):
            g = games[idx]
            gid = str(g["game_id"])
            del watched[gid]
            json_store.save_watched(watched)
            print(f"\n  Removed: {g['date']}  {g['away']} @ {g['home']}")
    input("\nPress Enter to continue...")


# ── Sort helper ──────────────────────────────────────────────────────────────

def _sort_prompt(cols: list[tuple[str, str, bool]]) -> tuple[str, bool] | None:
    """
    Display the action menu and return one of:
      (sort_key, reverse)  — user picked a sort column
      "csv"                — user wants a CSV export
      "limit"              — user wants to change head/tail limit
      None                 — user pressed q (go back)
      False                — invalid input (caller re-prompts)
    """
    print("\n  Sort by:")
    for i, (label, _, _) in enumerate(cols, 1):
        print(f"    [{i}] {label}")
    print("    [h] Show top N (head)")
    print("    [t] Show bottom N (tail)")
    print("    [c] Export to CSV")
    print("    [q] Back")
    cmd = input("\n  > ").strip().lower()
    if cmd == "q":
        return None
    if cmd == "c":
        return "csv"
    if cmd in ("h", "t"):
        return ("limit", cmd)
    if cmd.isdigit():
        idx = int(cmd) - 1
        if 0 <= idx < len(cols):
            _, key, rev = cols[idx]
            return key, rev
    return False   # invalid — caller re-prompts


def _ask_limit(current_limit: int | None, current_tail: bool) -> tuple[int | None, bool]:
    """
    Ask the user for a row limit and head/tail direction.
    Returns (limit, from_tail). limit=None means show all.
    """
    direction = "tail" if current_tail else "head"
    showing = f"{current_limit} ({direction})" if current_limit else "all"
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
    """Slice rows to the requested head or tail."""
    if limit is None:
        return rows
    return rows[-limit:] if from_tail else rows[:limit]


def _limit_label(limit: int | None, from_tail: bool) -> str:
    if limit is None:
        return "all rows"
    return f"bottom {limit}" if from_tail else f"top {limit}"



# ── CSV export helper ─────────────────────────────────────────────────────────

def _dump_csv(filename: str, headers: list[str], rows: list[dict], display_keys: list[str]) -> None:
    """
    Write the currently-sorted rows to a CSV file.
      filename     — output filename (no path, written to cwd)
      headers      — human-readable column headers
      rows         — already-sorted list of row dicts
      display_keys — keys from each row dict matching headers order
    """
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([r[k] for k in display_keys])
    print(f"\n  ✓ Exported {len(rows)} rows to {filename}")
    input("  Press Enter to continue...")


# ── Screen: Game Summary ──────────────────────────────────────────────────────

# Column definitions for game summary sort menu
#   (label, sort_key_in_row, high_is_best)
_GAME_SORT_COLS = [
    ("Team name",       "name",  False),
    ("Wins",            "W",     True),
    ("Losses",          "L",     False),
    ("Win %",           "pct",   True),
    ("Runs scored",     "rs",    True),
    ("Runs allowed",    "ra",    False),
    ("Games",           "g",     True),
    ("Runs/game",       "rpg",   True),
]


def summary(watched: dict):
    """Show per-team record and run stats across all watched games."""
    if not watched:
        clear()
        print_header("Game Summary")
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    scored = [
        g for g in watched.values()
        if g.get("away_score", "") != "" and g.get("home_score", "") != ""
    ]
    if not scored:
        clear()
        print_header("Game Summary")
        print("\n  No completed games with scores found.")
        input("\nPress Enter to continue...")
        return

    # Build per-team rows (compute once, sort on demand)
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

    def build_rows(sort_col="pct", reverse=True):
        rows = []
        for name, t in teams.items():
            total = t["W"] + t["L"]
            pct = t["W"] / total if total else 0
            rpg = t["rs"] / t["g"] if t["g"] else 0
            rows.append({
                "name": name, "W": t["W"], "L": t["L"],
                "pct": pct, "rs": t["rs"], "ra": t["ra"],
                "g": t["g"], "rpg": rpg,
            })
        rows.sort(key=lambda r: (r[sort_col] if isinstance(r[sort_col], (int, float))
                                 else r[sort_col].lower()),
                  reverse=reverse)
        return rows

    total_runs = sum(int(g["away_score"]) + int(g["home_score"]) for g in scored)
    avg_runs   = total_runs / len(scored)
    highest = max(scored, key=lambda g: int(g["away_score"]) + int(g["home_score"]))
    lowest  = min(scored, key=lambda g: int(g["away_score"]) + int(g["home_score"]))
    blowout = max(scored, key=lambda g: abs(int(g["away_score"]) - int(g["home_score"])))
    margin  = abs(int(blowout["away_score"]) - int(blowout["home_score"]))

    sort_col, sort_rev = "pct", True   # default sort
    limit, from_tail = 25, False           # default: top 25

    while True:
        rows = build_rows(sort_col, sort_rev)
        clear()
        print_header("Game Summary")
        sort_label = next(l for l, k, _ in _GAME_SORT_COLS if k == sort_col)
        visible = _apply_limit(rows, limit, from_tail)
        print(f"\n  {len(scored)} game(s)  |  {len(teams)} teams  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}\n")

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
        print(f"  🥱 Lowest-scoring:  {lowest['date']}   {lowest['away']} @ {lowest['home']}  ({lowest['away_score']}–{lowest['home_score']})")
        print(f"  💥 Biggest blowout: {blowout['date']}  {blowout['away']} @ {blowout['home']}  ({blowout['away_score']}–{blowout['home_score']}, margin: {margin})")

        result = _sort_prompt(_GAME_SORT_COLS)
        if result is None:
            return
        if result == "csv":
            csv_rows = [{**r, "pct": f"{r['pct']:.3f}", "rpg": f"{r['rpg']:.1f}"} for r in _apply_limit(rows, limit, from_tail)]
            _dump_csv(
                "game_summary.csv",
                ["Team", "W", "L", "PCT", "RS", "RA", "G", "R/G"],
                csv_rows,
                ["name", "W", "L", "pct", "rs", "ra", "g", "rpg"],
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
    """Sub-menu: choose pitchers or batters, then fetch and display leaderboard."""
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


# Column definitions for pitcher sort menu
_PITCH_SORT_COLS = [
    ("Name",        "name",  False),
    ("Team",        "team",  False),
    ("Appearances", "app",   True),
    ("IP",          "_outs", True),   # sort numerically on raw outs
    ("ERA",         "_era",  False),
    ("WHIP",        "_whip", False),
    ("K/9",         "_k9",   True),
    ("BB/9",        "_bb9",  False),
    ("HR/9",        "_hr9",  False),
]

# Column definitions for batter sort menu
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
    clear()
    print_header("Pitcher Summary")
    print(f"\n  Fetching boxscore data for {len(watched)} game(s)...\n")

    try:
        pitchers, _ = player_summary.collect_player_game_stats(watched)
    except Exception as e:
        print(f"\n  Error collecting stats: {e}")
        input("\nPress Enter to continue...")
        return

    rows = player_summary.pitching_leaderboard(pitchers)
    # attach raw outs for IP sort
    from player_summary import ip_to_outs
    for r in rows:
        r["_outs"] = ip_to_outs(r["ip"])

    if not rows:
        clear()
        print_header("Pitcher Summary")
        print(f"\n  Not enough data (need ≥{player_summary.MIN_PITCHER_OUTS} outs per pitcher).")
        input("\nPress Enter to continue...")
        return

    sort_col, sort_rev = "_era", False   # default: ERA ascending
    limit, from_tail = 25, False           # default: top 25

    while True:
        sorted_rows = sorted(
            rows,
            key=lambda r: (r[sort_col] if isinstance(r[sort_col], (int, float))
                           else r[sort_col].lower()),
            reverse=sort_rev,
        )
        clear()
        print_header("Pitcher Summary")
        sort_label = next(l for l, k, _ in _PITCH_SORT_COLS if k == sort_col)
        visible = _apply_limit(sorted_rows, limit, from_tail)
        print(f"\n  {len(rows)} pitchers  |  min {player_summary.MIN_PITCHER_OUTS} outs  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}\n")

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
                _apply_limit(sorted_rows, limit, from_tail),
                ["name", "team", "app", "ip", "era", "whip", "k9", "bb9", "hr9"],
            )
            continue
        if isinstance(result, tuple) and result[0] == "limit":
            limit, from_tail = _ask_limit(limit, result[1] == "t")
            continue
        if result is False:
            continue
        sort_col, sort_rev = result


def _show_batting(watched: dict):
    clear()
    print_header("Batter Summary")
    print(f"\n  Fetching boxscore data for {len(watched)} game(s)...\n")

    try:
        _, batters = player_summary.collect_player_game_stats(watched)
    except Exception as e:
        print(f"\n  Error collecting stats: {e}")
        input("\nPress Enter to continue...")
        return

    rows = player_summary.batting_leaderboard(batters)

    if not rows:
        clear()
        print_header("Batter Summary")
        print(f"\n  Not enough data (need ≥{player_summary.MIN_BATTER_AB} AB per batter).")
        input("\nPress Enter to continue...")
        return

    sort_col, sort_rev = "_ops", True   # default: OPS descending
    limit, from_tail = 25, False           # default: top 25

    while True:
        sorted_rows = sorted(
            rows,
            key=lambda r: (r[sort_col] if isinstance(r[sort_col], (int, float))
                           else r[sort_col].lower()),
            reverse=sort_rev,
        )
        clear()
        print_header("Batter Summary")
        sort_label = next(l for l, k, _ in _BAT_SORT_COLS if k == sort_col)
        visible = _apply_limit(sorted_rows, limit, from_tail)
        print(f"\n  {len(rows)} batters  |  min {player_summary.MIN_BATTER_AB} AB  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}\n")

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
                _apply_limit(sorted_rows, limit, from_tail),
                ["name", "team", "app", "ab", "h", "avg", "obp", "slg", "ops"],
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
