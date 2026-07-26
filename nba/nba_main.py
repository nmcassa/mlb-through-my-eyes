#!/usr/bin/env python3
"""
nba_main.py
NBA Watched Games Tracker — entry point.

A standalone sibling to the MLB tracker, pulling from ESPN's hidden API
(see espn_nba.py) instead of MLB-StatsAPI. Same shape: browse a team's
season and mark games you watched, then see summaries built ONLY from
those games.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

import espn_nba
import nba_player_summary as player_summary
import nba_json_store as json_store


# ── Display helpers ───────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  🏀  {title}")
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
        score = f"  [{status}]" if status else ""

    return f"{date}  {away} @ {home}{score}"


# ── Screen: Browse Season ─────────────────────────────────────────────────────

def browse_season(watched: dict):
    """Pick a team + season, then page through games to mark as watched."""
    print_header("Browse Season")

    team_query = input("\nEnter team name (e.g. Celtics, Lakers): ").strip()
    if not team_query:
        return

    try:
        results = espn_nba.find_teams(team_query)
    except RuntimeError as e:
        print(f"Error: {e}")
        input("\nPress Enter to continue...")
        return

    if not results:
        print("No team found. Try a different name.")
        input("\nPress Enter to continue...")
        return

    if len(results) > 1:
        print("\nMultiple teams found:")
        for i, t in enumerate(results):
            print(f"  [{i+1}] {t['name']}  ({t['abbreviation']})")
        choice = input("Select number: ").strip()
        try:
            team = results[int(choice) - 1]
        except (ValueError, IndexError):
            print("Invalid choice.")
            input("\nPress Enter to continue...")
            return
    else:
        team = results[0]

    season = input("\nEnter season year (the year it ENDS in — e.g. 2024 for the 2023-24 season): ").strip()
    if not season.isdigit():
        print("Invalid year.")
        input("\nPress Enter to continue...")
        return

    # Ask which season type(s) to include — the schedule endpoint only
    # returns one type per request, so postseason games are invisible
    # unless asked for explicitly.
    print("\n  Which part(s) of the season to include?\n")
    all_types = list(espn_nba.SEASON_TYPE_LABELS.items())  # [(code, label), ...]
    for i, (code, label) in enumerate(all_types, 1):
        print(f"    [{i}] {label}")
    print("\n  Enter numbers separated by spaces (e.g. '2 3' for regular season + playoffs)")
    print("  or press Enter for Regular Season only.")
    raw = input("\n  > ").strip()

    if not raw:
        season_types = ["2"]
    else:
        chosen = []
        for tok in raw.split():
            if tok.isdigit():
                idx = int(tok) - 1
                if 0 <= idx < len(all_types):
                    chosen.append(all_types[idx][0])
        season_types = chosen if chosen else ["2"]

    type_labels = ", ".join(espn_nba.SEASON_TYPE_LABELS.get(t, t) for t in season_types)
    print(f"\nFetching {team['name']} {season} schedule ({type_labels})...")
    try:
        games = espn_nba.fetch_team_schedule(team["id"], season, season_types=season_types)
    except RuntimeError as e:
        print(f"Error: {e}")
        input("\nPress Enter to continue...")
        return

    if not games:
        print("No games found for that team/season.")
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

def _apply_watched_filters(watched: dict, season_filter: str | None, team_filter: str | None) -> dict:
    """Return a subset of watched matching the active season and/or team filters."""
    out = {}
    for gid, g in watched.items():
        if season_filter and g["date"][:4] != season_filter:
            continue
        if team_filter and team_filter not in (g["away"], g["home"]):
            continue
        out[gid] = g
    return out


def _filters_label(season_filter: str | None, team_filter: str | None, min_min: float | None = None) -> str:
    parts = []
    if season_filter:
        parts.append(f"season={season_filter}")
    if team_filter:
        parts.append(f"team={team_filter}")
    if min_min is not None:
        parts.append(f"MIN≥{min_min:.0f}")
    return "  |  filters: " + ", ".join(parts) if parts else ""


def _filter_prompt(
    watched: dict,
    season_filter: str | None,
    team_filter: str | None,
    min_min: float | None = None,
    show_min: bool = False,
) -> tuple[str | None, str | None, float | None]:
    """Interactive filter menu. Returns (season_filter, team_filter, min_min)."""
    while True:
        clear()
        print_header("Filters")
        print("\n  ── Active filters ──────────────────────────────")
        print(f"    Season : {season_filter or 'all'}")
        print(f"    Team   : {team_filter or 'all'}")
        if show_min:
            print(f"    Min MIN: {min_min if min_min is not None else 'none'}")

        print("\n  ── Change filter ───────────────────────────────")
        print("    [1] Season")
        print("    [2] Team  (players on that team only)")
        if show_min:
            print("    [3] Min minutes watched")
        print("    [x] Clear all filters")
        print("    [q] Done")

        cmd = input("\n  > ").strip().lower()
        if cmd == "q":
            return season_filter, team_filter, min_min
        if cmd == "x":
            season_filter, team_filter, min_min = None, None, None
            continue
        if cmd == "1":
            seasons = sorted({g["date"][:4] for g in watched.values()})
            print(f"\n  Seasons watched: {', '.join(seasons) if seasons else 'none'}")
            raw = input("  Enter season (blank = all): ").strip()
            season_filter = raw or None
            continue
        if cmd == "2":
            teams = set()
            for g in watched.values():
                teams.add(g["away"]); teams.add(g["home"])
            print(f"\n  Teams watched: {', '.join(sorted(teams)) if teams else 'none'}")
            raw = input("  Enter team name (blank = all): ").strip()
            team_filter = raw or None
            continue
        if cmd == "3" and show_min:
            raw = input("  Minimum total minutes watched (blank = none): ").strip()
            if not raw:
                min_min = None
            else:
                try:
                    min_min = float(raw)
                except ValueError:
                    pass
            continue


# ── Sort / pagination helpers ─────────────────────────────────────────────────

def _sort_prompt(cols: list[tuple[str, str, bool]], total_pages: int = 1) -> object:
    """
    Display the action menu and return one of:
      (sort_key, reverse)     — user picked a sort column
      "csv"                   — export to CSV
      ("page", +1|-1)         — scroll to next/previous page
      ("pagesize", None)      — change rows-per-page
      "filter"                — open filter menu
      None                    — go back
      False                   — invalid input (re-prompt)
    """
    print("\n  Sort by:")
    for i, (label, _, _) in enumerate(cols, 1):
        print(f"    [{i}] {label}")
    if total_pages > 1:
        print("    [n] Next page   [p] Previous page")
    print("    [z] Rows per page")
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
    if cmd == "z":
        return ("pagesize", None)
    if cmd == "n" and total_pages > 1:
        return ("page", 1)
    if cmd == "p" and total_pages > 1:
        return ("page", -1)
    if cmd.isdigit():
        idx = int(cmd) - 1
        if 0 <= idx < len(cols):
            _, key, rev = cols[idx]
            return key, rev
    return False


def _ask_page_size(current: int | None) -> int | None:
    showing = f"{current} rows/page" if current else "all rows on one page"
    print(f"\n  Currently: {showing}")
    print("  Enter rows per page, or 0 to show everything on one page.")
    raw = input("  Rows per page: ").strip()
    if not raw.isdigit():
        return current
    n = int(raw)
    return None if n == 0 else n


def _paginate(rows: list, page: int, page_size: int | None) -> tuple[list, int, int]:
    """Slice rows into the requested page. page_size=None shows one page."""
    if not rows or not page_size:
        return rows, 0, 1
    total_pages = max(1, (len(rows) - 1) // page_size + 1)
    page  = max(0, min(page, total_pages - 1))
    start = page * page_size
    return rows[start:start + page_size], page, total_pages


def _page_label(page: int, total_pages: int) -> str:
    return f"page {page + 1}/{total_pages}" if total_pages > 1 else "all rows"


def _sort_rows(rows: list[dict], col: str, reverse: bool) -> list[dict]:
    """Sort rows by column, keeping None values (uncomputable Nick+) at the bottom."""
    present = [r for r in rows if r[col] is not None]
    missing = [r for r in rows if r[col] is None]
    present.sort(
        key=lambda r: r[col] if isinstance(r[col], (int, float)) else r[col].lower(),
        reverse=reverse,
    )
    return present + missing


def _dump_csv(filename: str, headers: list[str], rows: list[dict], keys: list[str]):
    with open(filename, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow([r.get(k, "") for k in keys])
    print(f"\n  ✓ Exported {len(rows)} rows to {filename}")
    input("  Press Enter to continue...")


# ── Screen: Game Summary ──────────────────────────────────────────────────────

_GAME_SORT_COLS = [
    ("Team name",     "name", False),
    ("Wins",          "W",    True),
    ("Losses",        "L",    False),
    ("Win %",         "pct",  True),
    ("Points scored", "ps",   True),
    ("Points allowed","pa",   False),
    ("Games",         "g",    True),
    ("Pts/game",      "ppg",  True),
]


def summary(watched: dict):
    """Show per-team record and scoring stats across all watched games."""
    if not watched:
        clear()
        print_header("Game Summary")
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    season_filter: str | None = None
    team_filter:   str | None = None

    sort_col, sort_rev = "pct", True
    page, page_size    = 0, 25

    while True:
        active = _apply_watched_filters(watched, season_filter, team_filter)
        scored = [
            g for g in active.values()
            if g.get("away_score", "") != "" and g.get("home_score", "") != ""
        ]

        teams: dict[str, dict] = {}
        def get_team(name):
            if name not in teams:
                teams[name] = {"W": 0, "L": 0, "ps": 0, "pa": 0, "g": 0}
            return teams[name]

        for g in scored:
            a = int(g["away_score"]); h = int(g["home_score"])
            at = get_team(g["away"]); ht = get_team(g["home"])
            at["g"] += 1; at["ps"] += a; at["pa"] += h
            ht["g"] += 1; ht["ps"] += h; ht["pa"] += a
            if a > h:   at["W"] += 1; ht["L"] += 1
            elif h > a: ht["W"] += 1; at["L"] += 1

        rows = []
        for name, t in teams.items():
            total = t["W"] + t["L"]
            pct   = t["W"] / total if total else 0
            ppg   = t["ps"] / t["g"] if t["g"] else 0
            rows.append({
                "name": name, "W": t["W"], "L": t["L"],
                "pct": pct, "ps": t["ps"], "pa": t["pa"],
                "g": t["g"], "ppg": ppg,
            })

        rows.sort(
            key=lambda r: r[sort_col] if isinstance(r[sort_col], (int, float)) else r[sort_col].lower(),
            reverse=sort_rev,
        )
        visible, page, total_pages = _paginate(rows, page, page_size)

        clear()
        print_header("Game Summary")
        sort_label = next(l for l, k, _ in _GAME_SORT_COLS if k == sort_col)
        fl = _filters_label(season_filter, team_filter)
        print(f"\n  {len(scored)} game(s)  |  {len(teams)} teams  |  sorted by {sort_label}  |  {_page_label(page, total_pages)}{fl}\n")

        if not scored:
            print("  No completed games match current filters.")
        else:
            total_pts = sum(int(g["away_score"]) + int(g["home_score"]) for g in scored)
            avg_pts   = total_pts / len(scored)
            highest = max(scored, key=lambda g: int(g["away_score"]) + int(g["home_score"]))
            lowest  = min(scored, key=lambda g: int(g["away_score"]) + int(g["home_score"]))
            blowout = max(scored, key=lambda g: abs(int(g["away_score"]) - int(g["home_score"])))
            margin  = abs(int(blowout["away_score"]) - int(blowout["home_score"]))

            col = "{:<26}  {:>3}  {:>3}  {:>5}  {:>6}  {:>6}  {:>5}  {:>6}"
            print(col.format("Team", "W", "L", "PCT", "PS", "PA", "G", "PTS/G"))
            print("  " + "-" * 58)
            for r in visible:
                print("  " + col.format(
                    r["name"][:26], r["W"], r["L"],
                    f"{r['pct']:.3f}", r["ps"], r["pa"],
                    r["g"], f"{r['ppg']:.1f}",
                ))

            print("\n" + "-" * 60)
            print(f"  Avg total points/game: {avg_pts:.1f}")
            print(f"  🔥 Highest-scoring: {highest['date']}  {highest['away']} @ {highest['home']}  ({highest['away_score']}–{highest['home_score']})")
            print(f"  🥱 Lowest-scoring:  {lowest['date']}  {lowest['away']} @ {lowest['home']}  ({lowest['away_score']}–{lowest['home_score']})")
            print(f"  💥 Biggest blowout: {blowout['date']}  {blowout['away']} @ {blowout['home']}  ({blowout['away_score']}–{blowout['home_score']}, margin: {margin})")

        result = _sort_prompt(_GAME_SORT_COLS, total_pages)
        if result is None:
            return
        if result == "csv":
            csv_rows = [{**r, "pct": f"{r['pct']:.3f}", "ppg": f"{r['ppg']:.1f}"} for r in visible]
            _dump_csv(
                "nba_game_summary.csv",
                ["Team", "W", "L", "PCT", "PS", "PA", "G", "PTS/G"],
                csv_rows,
                ["name", "W", "L", "pct", "ps", "pa", "g", "ppg"],
            )
            continue
        if result == "filter":
            season_filter, team_filter, _ = _filter_prompt(watched, season_filter, team_filter)
            page = 0
            continue
        if isinstance(result, tuple) and result[0] == "pagesize":
            page_size = _ask_page_size(page_size)
            page = 0
            continue
        if isinstance(result, tuple) and result[0] == "page":
            page += result[1]
            continue
        if result is False:
            continue
        sort_col, sort_rev = result
        page = 0


# ── Screen: Player Summary ────────────────────────────────────────────────────

_PLAYER_SORT_COLS = [
    ("Name",         "name",     False),
    ("Team",         "team",     False),
    ("Appearances",  "app",      True),
    ("Nick+",        "nickplus", True),
    ("Minutes",      "min",      True),
    ("PPG",          "_ppg",     True),
    ("RPG",          "_rpg",     True),
    ("APG",          "_apg",     True),
    ("SPG",          "_spg",     True),
    ("BPG",          "_bpg",     True),
    ("TOPG",         "_topg",    False),
    ("FG%",          "_fg_pct",  True),
    ("3P%",          "_tp_pct",  True),
    ("FT%",          "_ft_pct",  True),
    ("Game Score",   "_gmsc",    True),
]


def _show_players(watched: dict):
    season_filter: str | None = None
    team_filter:   str | None = None
    min_min:       float | None = None

    sort_col, sort_rev = "nickplus", True
    page, page_size    = 0, 25

    # ── Step 1: ask for filters BEFORE any expensive fetching ────────────────
    clear()
    print_header("Player Summary")
    print("\n  Set filters before loading (reduces games fetched).\n")
    print(f"  Watched games: {len(watched)}\n")
    season_filter, team_filter, min_min = _filter_prompt(
        watched, season_filter, team_filter, min_min=min_min, show_min=True
    )

    fetch_watched = _apply_watched_filters(watched, season_filter, team_filter)
    clear()
    print_header("Player Summary")
    print(f"\n  Fetching box score data for {len(fetch_watched)} game(s) (filtered from {len(watched)} total)...\n")
    try:
        all_players = player_summary.collect_player_game_stats(fetch_watched)
    except Exception as e:
        print(f"\n  Error collecting stats: {e}")
        input("\nPress Enter to continue...")
        return

    while True:
        players_raw = player_summary.filter_and_aggregate(
            all_players,
            season_filter=None,         # already applied at fetch time
            team_filter=team_filter,    # still needed to exclude opponents
        )
        rows = player_summary.player_leaderboard(players_raw, min_min=min_min)
        player_summary.annotate_nick_plus(rows)   # pool = this qualifying leaderboard

        sorted_rows = _sort_rows(rows, sort_col, sort_rev)
        visible, page, total_pages = _paginate(sorted_rows, page, page_size)

        clear()
        print_header("Player Summary")
        sort_label = next(l for l, k, _ in _PLAYER_SORT_COLS if k == sort_col)
        fl = _filters_label(season_filter, team_filter, min_min=min_min)
        print(f"\n  {len(rows)} players  |  sorted by {sort_label}  |  {_page_label(page, total_pages)}{fl}\n")
        print("  Nick+: 100 = average of these players, weighted by how much you've watched them. Higher is better.\n")

        if not rows:
            print("  No players match current filters.")
        else:
            col = "{:<20}  {:<18}  {:>4}  {:>6}  {:>6}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}"
            print(col.format("Name", "Team", "App", "Nick+", "MIN", "PPG", "RPG", "APG", "SPG", "BPG", "TOPG", "FG%", "3P%", "FT%"))
            print("  " + "-" * 122)
            for r in visible:
                print("  " + col.format(
                    r["name"][:20], r["team"][:18],
                    r["app"], r["nick+"], f"{r['min']:.0f}",
                    r["ppg"], r["rpg"], r["apg"], r["spg"], r["bpg"], r["topg"],
                    r["fg_pct"], r["tp_pct"], r["ft_pct"],
                ))
            if total_pages > 1:
                print(f"\n  Press [n]/[p] to scroll pages.")

        result = _sort_prompt(_PLAYER_SORT_COLS, total_pages)
        if result is None:
            return
        if result == "csv":
            _dump_csv(
                "nba_player_summary.csv",
                ["Name", "Team", "App", "Nick+", "MIN", "PPG", "RPG", "APG", "SPG", "BPG", "TOPG",
                 "FGM", "FGA", "FG%", "3PM", "3PA", "3P%", "FTM", "FTA", "FT%", "GameScore"],
                visible,
                ["name", "team", "app", "nick+", "min", "ppg", "rpg", "apg", "spg", "bpg", "topg",
                 "fgm", "fga", "fg_pct", "3pm", "3pa", "tp_pct", "ftm", "fta", "ft_pct", "gmsc"],
            )
            continue
        if result == "filter":
            new_sf, new_tf, new_min = _filter_prompt(
                watched, season_filter, team_filter, min_min=min_min, show_min=True
            )
            if (new_sf, new_tf) != (season_filter, team_filter):
                season_filter, team_filter, min_min = new_sf, new_tf, new_min
                fetch_watched = _apply_watched_filters(watched, season_filter, team_filter)
                clear()
                print_header("Player Summary")
                print(f"\n  Re-fetching box score data for {len(fetch_watched)} game(s)...\n")
                try:
                    all_players = player_summary.collect_player_game_stats(fetch_watched)
                except Exception as e:
                    print(f"\n  Error: {e}")
                    input("\nPress Enter to continue...")
                    return
            else:
                season_filter, team_filter, min_min = new_sf, new_tf, new_min
            page = 0
            continue
        if isinstance(result, tuple) and result[0] == "pagesize":
            page_size = _ask_page_size(page_size)
            page = 0
            continue
        if isinstance(result, tuple) and result[0] == "page":
            page += result[1]
            continue
        if result is False:
            continue
        sort_col, sort_rev = result
        page = 0


# ── Screen: Search Player ─────────────────────────────────────────────────────

def screen_player_search(watched: dict):
    """Search for a player by name and see a season-by-season breakdown of
    the games you've logged for them (one row per watched season)."""
    if not watched:
        clear()
        print_header("Search Player")
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    while True:
        clear()
        print_header("Search Player")
        print(f"\n  Searching across {len(watched)} watched game(s).")
        query = input("\n  Player name (or part of it), or 'q' to go back: ").strip()
        if query.lower() == "q":
            return
        if not query:
            continue

        clear()
        print_header("Search Player")
        print(f"\n  Fetching box score data for {len(watched)} game(s)...\n")
        try:
            all_players = player_summary.collect_player_game_stats(watched)
        except Exception as e:
            print(f"\n  Error collecting stats: {e}")
            input("\nPress Enter to continue...")
            return

        q = query.lower()
        matches = sorted(n for n in all_players.keys() if q in n.lower())

        if not matches:
            print(f"\n  No players matching '{query}' found in your watched games.")
            input("\nPress Enter to continue...")
            continue

        # Nick+ pool: every qualifying player across your ENTIRE watched
        # history, so a player's score means "compared to everyone you've
        # watched" consistently.
        pool_raw  = player_summary.filter_and_aggregate(all_players)
        pool_rows = player_summary.player_leaderboard(pool_raw)
        baseline  = player_summary.compute_pool_baseline(pool_rows)

        if len(matches) == 1:
            name = matches[0]
        else:
            clear()
            print_header("Search Player")
            print(f"\n  {len(matches)} players match '{query}':\n")
            for i, n in enumerate(matches, 1):
                print(f"    [{i}] {n}")
            print("    [q] Back")
            sel = input("\n  > ").strip().lower()
            if sel == "q":
                continue
            if not sel.isdigit() or not (1 <= int(sel) <= len(matches)):
                continue
            name = matches[int(sel) - 1]

        _show_player_seasons(name, all_players.get(name), baseline)


def _show_player_seasons(name: str, player_data: dict | None, baseline: dict | None):
    """Render a per-season table for one player."""
    while True:
        clear()
        print_header(f"Season Log — {name}")

        rows = player_summary.player_season_rows(name, player_data["games"]) if player_data else []
        for r in rows:
            n = player_summary.nick_plus(r, baseline)
            r["nickplus"], r["nick+"] = n, (str(n) if n is not None else "—")

        if rows:
            print("\n  Nick+: 100 = average of every qualifying player you've watched. Higher is better.\n")
            col = "  {:<14}  {:<18}  {:>4}  {:>6}  {:>6}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}"
            print(col.format("Season", "Team", "App", "Nick+", "MIN", "PPG", "RPG", "APG", "SPG", "BPG", "TOPG", "FG%", "3P%", "FT%"))
            print("  " + "-" * 122)
            for r in rows:
                print(col.format(
                    r["season"], r["team"][:18], r["app"], r["nick+"], f"{r['min']:.0f}",
                    r["ppg"], r["rpg"], r["apg"], r["spg"], r["bpg"], r["topg"],
                    r["fg_pct"], r["tp_pct"], r["ft_pct"],
                ))
        else:
            print("\n  No qualifying games found for this player.")

        print("\n  [c] Export to CSV")
        print("  [q] Back")
        cmd = input("\n  > ").strip().lower()
        if cmd == "q":
            return
        if cmd == "c" and rows:
            safe_name = name.replace(" ", "_").replace("/", "_")
            _dump_csv(
                f"{safe_name}_nba_by_season.csv",
                ["Season", "Team", "App", "Nick+", "MIN", "PPG", "RPG", "APG", "SPG", "BPG", "TOPG",
                 "FGM", "FGA", "FG%", "3PM", "3PA", "3P%", "FTM", "FTA", "FT%", "GameScore"],
                rows,
                ["season", "team", "app", "nick+", "min", "ppg", "rpg", "apg", "spg", "bpg", "topg",
                 "fgm", "fga", "fg_pct", "3pm", "3pa", "tp_pct", "ftm", "fta", "ft_pct", "gmsc"],
            )


# ── Main menu ─────────────────────────────────────────────────────────────────

def main():
    watched = json_store.load_watched()

    while True:
        watched = json_store.load_watched()
        clear()
        print_header("NBA Watched Games Tracker")
        print(f"\n  {len(watched)} game(s) watched  |  file: {json_store.watched_file_path()}\n")
        print("  [1]  Browse a season & mark games watched")
        print("  [2]  View all watched games")
        print("  [3]  Remove a watched game")
        print("  [4]  Game Summary")
        print("  [5]  Player Summary")
        print("  [6]  Search Player")
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
            _show_players(watched)
        elif cmd == "6":
            screen_player_search(watched)
        elif cmd == "q":
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
