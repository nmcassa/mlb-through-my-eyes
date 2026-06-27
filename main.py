#!/usr/bin/env python3
"""
MLB Watched Games Tracker
Track which games you've watched and save them to a JSON file.
"""

import json
import os
import sys
from datetime import datetime

try:
    import statsapi
except ImportError:
    print("Error: MLB-StatsAPI not installed. Run: pip install MLB-StatsAPI")
    sys.exit(1)

WATCHED_FILE = "watched_games.json"


# ── JSON helpers ──────────────────────────────────────────────────────────────

def load_watched():
    if os.path.exists(WATCHED_FILE):
        with open(WATCHED_FILE) as f:
            return json.load(f)
    return {}


def save_watched(data):
    with open(WATCHED_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Display helpers ───────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  ⚾  {title}")
    print("=" * 60)


def game_label(game):
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


# ── Core screens ──────────────────────────────────────────────────────────────

def browse_season(watched):
    """Pick a team + season, then browse games to mark as watched."""
    print_header("Browse Season")

    team_query = input("\nEnter team name (e.g. Braves, Yankees): ").strip()
    if not team_query:
        return

    results = statsapi.lookup_team(team_query)
    if not results:
        print("No team found. Try a different name.")
        input("\nPress Enter to continue...")
        return

    # If multiple hits, let the user pick
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

    season = input(f"\nEnter season year (e.g. 2014): ").strip()
    if not season.isdigit():
        print("Invalid year.")
        input("\nPress Enter to continue...")
        return

    print(f"\nFetching {team['name']} {season} schedule...")
    try:
        schedule = statsapi.schedule(
            team=team["id"],
            start_date=f"{season}-01-01",
            end_date=f"{season}-12-31",
            sportId=1,
        )
    except Exception as e:
        print(f"Error fetching schedule: {e}")
        input("\nPress Enter to continue...")
        return

    # Regular season only
    games = [g for g in schedule if g.get("game_type") == "R"]
    if not games:
        print("No regular season games found.")
        input("\nPress Enter to continue...")
        return

    _game_select_loop(games, watched, team["name"], season)


def _game_select_loop(games, watched, team_name, season):
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
                        "team_followed": None,  # set below
                        "added_at": datetime.now().isoformat(),
                    }
                    print(f"\n  ★ Added:   {game_label(game)}")
                save_watched(watched)
                input("  Press Enter to continue...")
        else:
            pass  # ignore unknown input


def view_watched(watched):
    """List all watched games."""
    clear()
    print_header("My Watched Games")

    if not watched:
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    # Group by year
    by_year = {}
    for gid, g in watched.items():
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


def remove_watched(watched):
    """Remove a game from watched list."""
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
            save_watched(watched)
            print(f"\n  Removed: {g['date']}  {g['away']} @ {g['home']}")
    input("\nPress Enter to continue...")


# ── Main menu ─────────────────────────────────────────────────────────────────

def main():
    while True:
        watched = load_watched()
        clear()
        print_header("MLB Watched Games Tracker")
        print(f"\n  Games watched: {len(watched)}")
        print(f"  Data file:     {os.path.abspath(WATCHED_FILE)}\n")
        print("  [1]  Browse a season & mark games watched")
        print("  [2]  View all watched games")
        print("  [3]  Remove a watched game")
        print("  [q]  Quit\n")

        cmd = input("> ").strip().lower()

        if cmd == "1":
            browse_season(watched)
        elif cmd == "2":
            view_watched(watched)
        elif cmd == "3":
            remove_watched(watched)
        elif cmd == "q":
            print("\nBye!\n")
            break


if __name__ == "__main__":
    main()
