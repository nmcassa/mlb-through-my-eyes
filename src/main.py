#!/usr/bin/env python3
"""
main.py
MLB Watched Games Tracker — entry point.
All UI screens and the main menu loop live here.
"""

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


# ── Screen: Summary ───────────────────────────────────────────────────────────

def summary(watched: dict):
    """Show per-team record and run stats across all watched games."""
    clear()
    print_header("Watched Games Summary")

    if not watched:
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    scored = [
        g for g in watched.values()
        if g.get("away_score", "") != "" and g.get("home_score", "") != ""
    ]

    if not scored:
        print("\n  No completed games with scores found.")
        input("\nPress Enter to continue...")
        return

    # Build per-team stats
    teams: dict[str, dict] = {}

    def get_team(name: str) -> dict:
        if name not in teams:
            teams[name] = {"W": 0, "L": 0, "runs_scored": 0, "runs_allowed": 0, "games": 0}
        return teams[name]

    for g in scored:
        a_sc = int(g["away_score"])
        h_sc = int(g["home_score"])

        away_t = get_team(g["away"])
        home_t = get_team(g["home"])

        away_t["games"] += 1
        away_t["runs_scored"] += a_sc
        away_t["runs_allowed"] += h_sc

        home_t["games"] += 1
        home_t["runs_scored"] += h_sc
        home_t["runs_allowed"] += a_sc

        if a_sc > h_sc:
            away_t["W"] += 1
            home_t["L"] += 1
        elif h_sc > a_sc:
            home_t["W"] += 1
            away_t["L"] += 1

    def sort_key(item):
        t = item[1]
        total = t["W"] + t["L"]
        pct = t["W"] / total if total else 0
        return (-pct, -t["W"])

    sorted_teams = sorted(teams.items(), key=sort_key)

    total_runs = sum(int(g["away_score"]) + int(g["home_score"]) for g in scored)
    avg_runs = total_runs / len(scored)

    print(f"\n  {len(scored)} completed game{'s' if len(scored) != 1 else ''} across {len(teams)} teams\n")

    col = "{:<26}  {:>3}  {:>3}  {:>5}  {:>6}  {:>6}  {:>5}  {:>6}"
    print(col.format("Team", "W", "L", "PCT", "RS", "RA", "G", "R/G"))
    print("  " + "-" * 58)

    for name, t in sorted_teams:
        total = t["W"] + t["L"]
        pct = t["W"] / total if total else 0
        rpg = t["runs_scored"] / t["games"] if t["games"] else 0
        print("  " + col.format(
            name[:26],
            t["W"], t["L"],
            f"{pct:.3f}",
            t["runs_scored"], t["runs_allowed"],
            t["games"],
            f"{rpg:.1f}",
        ))

    print("\n" + "-" * 60)
    print(f"  Avg runs per game (both teams): {avg_runs:.1f}")

    highest = max(scored, key=lambda g: int(g["away_score"]) + int(g["home_score"]))
    lowest  = min(scored, key=lambda g: int(g["away_score"]) + int(g["home_score"]))
    blowout = max(scored, key=lambda g: abs(int(g["away_score"]) - int(g["home_score"])))
    margin  = abs(int(blowout["away_score"]) - int(blowout["home_score"]))

    print(f"\n  🔥 Highest-scoring:  {highest['date']}  {highest['away']} @ {highest['home']}  ({highest['away_score']}–{highest['home_score']})")
    print(f"  🥱 Lowest-scoring:   {lowest['date']}  {lowest['away']} @ {lowest['home']}  ({lowest['away_score']}–{lowest['home_score']})")
    print(f"  💥 Biggest blowout:  {blowout['date']}  {blowout['away']} @ {blowout['home']}  ({blowout['away_score']}–{blowout['home_score']}, margin: {margin})")

    print()
    input("Press Enter to continue...")


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

    clear()
    print_header("Pitcher Summary")

    if not rows:
        print(f"\n  Not enough data yet (need ≥{player_summary.MIN_PITCHER_OUTS} outs per pitcher).")
        input("\nPress Enter to continue...")
        return

    print(f"\n  {len(rows)} pitchers  |  min {player_summary.MIN_PITCHER_OUTS} outs  |  sorted by ERA\n")

    col = "{:<25}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>4}"
    print(col.format("Name", "App", "IP", "ERA", "WHIP", "K/9", "BB/9", "HR/9"))
    print("  " + "-" * 62)
    for r in rows:
        print("  " + col.format(
            r["name"][:25],
            r["app"],
            r["ip"],
            r["era"],
            r["whip"],
            r["k9"],
            r["bb9"],
            r["hr9"],
        ))

    print()
    input("Press Enter to continue...")


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

    clear()
    print_header("Batter Summary")

    if not rows:
        print(f"\n  Not enough data yet (need ≥{player_summary.MIN_BATTER_AB} AB per batter).")
        input("\nPress Enter to continue...")
        return

    print(f"\n  {len(rows)} batters  |  min {player_summary.MIN_BATTER_AB} AB  |  sorted by OPS\n")

    col = "{:<25}  {:>4}  {:>4}  {:>6}  {:>5}  {:>5}  {:>5}"
    print(col.format("Name", "App", "AB", "AVG", "OBP", "SLG", "OPS"))
    print("  " + "-" * 56)
    for r in rows:
        print("  " + col.format(
            r["name"][:25],
            r["app"],
            r["ab"],
            r["avg"],
            r["obp"],
            r["slg"],
            r["ops"],
        ))

    print()
    input("Press Enter to continue...")



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
