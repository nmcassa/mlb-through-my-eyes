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
import comparison
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
    ip_min: float | None = None,
    pa_min: int | None = None,
) -> str:
    parts = []
    if season_filter:
        parts.append(f"season={season_filter}")
    if team_filter:
        parts.append(f"team={team_filter}")
    if ip_min is not None:
        parts.append(f"IP≥{ip_min:.1f}")
    if pa_min is not None:
        parts.append(f"PA≥{pa_min}")
    return "  |  filters: " + ", ".join(parts) if parts else ""


def _filter_prompt(
    watched: dict,
    season_filter: str | None,
    team_filter: str | None,
    ip_min: float | None = None,
    pa_min: int | None = None,
    show_ip: bool = False,
    show_pa: bool = False,
) -> tuple[str | None, str | None, float | None, int | None]:
    """
    Interactive filter menu. Returns (season_filter, team_filter, ip_min, pa_min).
    season/team filters are applied per-game-record in memory (no re-fetch).
    team_filter matches only players who were on that team in that game.
    """
    seasons = _all_seasons(watched)
    teams   = _all_teams(watched)

    while True:
        print("\n  ── Active filters ──────────────────────────────")
        print(f"    Season : {season_filter or 'all'}")
        print(f"    Team   : {team_filter   or 'all'}")
        if show_ip:
            print(f"    Min IP : {ip_min:.1f}" if ip_min is not None else "    Min IP : none")
        if show_pa:
            print(f"    Min PA : {pa_min}" if pa_min is not None else "    Min PA : none")

        print("\n  ── Change filter ───────────────────────────────")
        print("    [1] Season")
        print("    [2] Team  (players on that team only)")
        if show_ip:
            print("    [3] Min IP")
        if show_pa:
            print("    [3] Min PA")
        print("    [x] Clear all filters")
        print("    [q] Done")
        cmd = input("\n  > ").strip().lower()

        if cmd == "q":
            return season_filter, team_filter, ip_min, pa_min

        elif cmd == "x":
            season_filter, team_filter, ip_min, pa_min = None, None, None, None
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

        elif cmd == "3" and show_pa:
            raw = input("  Minimum PA (e.g. 10), or 0 to clear: ").strip()
            try:
                val = int(raw)
                pa_min = None if val == 0 else val
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
    ("PA",          "pa",    True),
    ("AB",          "ab",    True),
    ("AVG",         "_avg",  True),
    ("OBP",         "_obp",  True),
    ("SLG",         "_slg",  True),
    ("OPS",         "_ops",  True),
]


def _show_pitching(watched: dict):
    season_filter: str | None  = None
    team_filter:   str | None  = None
    ip_min:        float | None = None

    sort_col, sort_rev = "_era", False
    limit, from_tail   = 25, False

    # Fetch once — all filtering happens in memory via filter_and_aggregate
    clear()
    print_header("Pitcher Summary")
    print(f"\n  Fetching boxscore data for {len(watched)} game(s)...\n")
    try:
        all_pitchers, all_batters = player_summary.collect_player_game_stats(watched)
    except Exception as e:
        print(f"\n  Error collecting stats: {e}")
        input("\nPress Enter to continue...")
        return

    while True:
        pitchers_raw, _ = player_summary.filter_and_aggregate(
            all_pitchers, all_batters,
            season_filter=season_filter,
            team_filter=team_filter,
        )
        rows = player_summary.pitching_leaderboard(pitchers_raw, ip_min=ip_min)

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
        fl = _filters_label(season_filter, team_filter, ip_min=ip_min)
        print(f"\n  {len(rows)} pitchers  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}{fl}\n")

        if not rows:
            print("  No pitchers match current filters.")
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
            season_filter, team_filter, ip_min, _ = _filter_prompt(
                watched, season_filter, team_filter, ip_min=ip_min, show_ip=True
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
    pa_min:        int | None = None

    sort_col, sort_rev = "_ops", True
    limit, from_tail   = 25, False

    # Fetch once — all filtering happens in memory via filter_and_aggregate
    clear()
    print_header("Batter Summary")
    print(f"\n  Fetching boxscore data for {len(watched)} game(s)...\n")
    try:
        all_pitchers, all_batters = player_summary.collect_player_game_stats(watched)
    except Exception as e:
        print(f"\n  Error collecting stats: {e}")
        input("\nPress Enter to continue...")
        return

    while True:
        _, batters_raw = player_summary.filter_and_aggregate(
            all_pitchers, all_batters,
            season_filter=season_filter,
            team_filter=team_filter,
        )
        rows = player_summary.batting_leaderboard(batters_raw, pa_min=pa_min)

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
        fl = _filters_label(season_filter, team_filter, pa_min=pa_min)
        print(f"\n  {len(rows)} batters  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}{fl}\n")

        if not rows:
            print("  No batters match current filters.")
        else:
            col = "{:<22}  {:<22}  {:>4}  {:>5}  {:>5}  {:>5}  {:>6}  {:>5}  {:>5}  {:>5}"
            print(col.format("Name", "Team", "App", "PA", "AB", "H", "AVG", "OBP", "SLG", "OPS"))
            print("  " + "-" * 85)
            for r in visible:
                print("  " + col.format(
                    r["name"][:22], r["team"][:22],
                    r["app"], r["pa"], r["ab"], r["h"],
                    r["avg"], r["obp"], r["slg"], r["ops"],
                ))

        result = _sort_prompt(_BAT_SORT_COLS)
        if result is None:
            return
        if result == "csv":
            _dump_csv(
                "batter_summary.csv",
                ["Name", "Team", "App", "PA", "AB", "H", "AVG", "OBP", "SLG", "OPS"],
                visible,
                ["name", "team", "app", "pa", "ab", "h", "avg", "obp", "slg", "ops"],
            )
            continue
        if result == "filter":
            season_filter, team_filter, _, pa_min = _filter_prompt(
                watched, season_filter, team_filter, pa_min=pa_min, show_pa=True
            )
            continue
        if isinstance(result, tuple) and result[0] == "limit":
            limit, from_tail = _ask_limit(limit, result[1] == "t")
            continue
        if result is False:
            continue
        sort_col, sort_rev = result



# ── Screen: Small Sample Comparison ──────────────────────────────────────────

_COMP_PITCH_SORT_COLS = [
    ("Name",          "name",    False),
    ("Team",          "team",    False),
    ("App",           "app",     True),
    ("Watched IP",    "w_ip",    True),
    ("Watched ERA",   "_w_era",  False),
    ("Watched WHIP",  "_w_whip", False),
    ("Watched K/9",   "_w_k9",   True),
    ("Watched BB/9",  "_w_bb9",  False),
    ("Watched HR/9",  "_w_hr9",  False),
    ("ERA Δ",         "d_era",   False),
    ("WHIP Δ",        "d_whip",  False),
    ("K/9 Δ",         "d_k9",    True),
    ("BB/9 Δ",        "d_bb9",   False),
    ("HR/9 Δ",        "d_hr9",   False),
]

_COMP_BAT_SORT_COLS = [
    ("Name",         "name",    False),
    ("Team",         "team",    False),
    ("App",          "app",     True),
    ("Watched PA",   "w_pa",    True),
    ("Watched AVG",  "_w_avg",  True),
    ("Watched OBP",  "_w_obp",  True),
    ("Watched SLG",  "_w_slg",  True),
    ("Watched OPS",  "_w_ops",  True),
    ("AVG Δ",        "d_avg",   True),
    ("OBP Δ",        "d_obp",   True),
    ("SLG Δ",        "d_slg",   True),
    ("OPS Δ",        "d_ops",   True),
]


def screen_small_sample(watched: dict):
    """Sub-menu: compare watched-game stats to career/season reference."""
    if not watched:
        clear()
        print_header("My Small Sample")
        print("\n  No games watched yet. Browse a season to add some!")
        input("\nPress Enter to continue...")
        return

    while True:
        clear()
        print_header("My Small Sample")
        print(f"\n  Compare watched-game performance to season/career averages.")
        print(f"  Season filter → uses that season's stats as reference.")
        print(f"  No season filter → uses career stats as reference.\n")
        print("  [1]  Pitchers")
        print("  [2]  Batters")
        print("  [q]  Back\n")
        cmd = input("> ").strip().lower()
        if cmd == "q":
            return
        elif cmd == "1":
            _show_comp_pitching(watched)
        elif cmd == "2":
            _show_comp_batting(watched)


def _show_comp_pitching(watched: dict):
    season_filter: str | None  = None
    team_filter:   str | None  = None
    ip_min:        float | None = None
    sort_col, sort_rev = "_w_era", False
    limit, from_tail   = 25, False

    # ── Step 1: ask for filters BEFORE any expensive fetching ────────────────
    clear()
    print_header("Small Sample — Pitchers")
    print("\n  Set filters before loading (reduces players fetched).\n")
    print(f"  Watched games: {len(watched)}")
    print(f"  Tip: set a Team filter to load only ~15-25 players instead of hundreds.\n")
    season_filter, team_filter, ip_min, _ = _filter_prompt(
        watched, season_filter, team_filter, ip_min=ip_min, show_ip=True
    )

    # ── Step 2: fetch boxscore data once ─────────────────────────────────────
    clear()
    print_header("Small Sample — Pitchers")
    print(f"\n  Fetching boxscore data for {len(watched)} game(s)...\n")
    try:
        all_pitchers, all_batters = player_summary.collect_player_game_stats(watched)
    except Exception as e:
        print(f"\n  Error: {e}")
        input("\nPress Enter to continue...")
        return

    # need_ref_fetch tracks when filters change and we must re-call the API
    need_ref_fetch = True
    rows: list = []

    while True:
        if need_ref_fetch:
            pitchers_raw, _ = player_summary.filter_and_aggregate(
                all_pitchers, all_batters,
                season_filter=season_filter,
                team_filter=team_filter,
            )
            ref_type = f"{season_filter} season" if season_filter else "career"
            leaderboard_size = len(player_summary.pitching_leaderboard(pitchers_raw, ip_min=ip_min))

            clear()
            print_header("Small Sample — Pitchers")
            fl = _filters_label(season_filter, team_filter, ip_min=ip_min)
            print(f"\n  Fetching {ref_type} ref stats for {leaderboard_size} pitchers{fl}...\n")
            rows = comparison.build_pitcher_rows(pitchers_raw, ip_min=ip_min, season_filter=season_filter)
            need_ref_fetch = False

        try:
            sorted_rows = sorted(
                rows,
                key=lambda r: (float(r[sort_col].lstrip("▲▼ +-")) if isinstance(r[sort_col], str) and r[sort_col] not in ("—", "")
                               else r[sort_col] if isinstance(r[sort_col], (int, float)) else r[sort_col].lower()),
                reverse=sort_rev,
            )
        except Exception:
            sorted_rows = rows

        visible = _apply_limit(sorted_rows, limit, from_tail)

        clear()
        print_header("Small Sample — Pitchers")
        sort_label = next(l for l, k, _ in _COMP_PITCH_SORT_COLS if k == sort_col)
        fl = _filters_label(season_filter, team_filter, ip_min=ip_min)
        print(f"\n  {len(rows)} pitchers  |  ref: {ref_type}  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}{fl}\n")

        if not rows:
            print("  No pitchers match current filters.")
        else:
            n = "{:<22}  {:<18}  {:>4}"
            s = "  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}"
            print("  " + n.format("Name", "Team", "App") + s.format("ERA", "WHIP", "K/9", "BB/9", "HR/9"))
            print("  " + "-"*22 + "  " + "-"*18 + "  " + "-"*4 + ("  " + "-"*5)*5)
            for r in visible:
                base = n.format(r["name"][:22], r["team"][:18], r["app"])
                print("  " + base + s.format(r["w_era"], r["w_whip"], r["w_k9"], r["w_bb9"], r["w_hr9"]) + "  ← watched")
                print("  " + " "*46 + s.format(r["r_era"], r["r_whip"], r["r_k9"], r["r_bb9"], r["r_hr9"]) + f"  ← {ref_type}")
                print("  " + " "*46 + s.format(r["d_era"], r["d_whip"], r["d_k9"], r["d_bb9"], r["d_hr9"]) + "  ← delta")
                print()

        result = _sort_prompt(_COMP_PITCH_SORT_COLS)
        if result is None:
            return
        if result == "csv":
            _dump_csv(
                "comp_pitcher.csv",
                ["Name","Team","App","W-IP","W-ERA","W-WHIP","W-K9","W-BB9","W-HR9",
                 "R-ERA","R-WHIP","R-K9","R-BB9","R-HR9",
                 "D-ERA","D-WHIP","D-K9","D-BB9","D-HR9"],
                visible,
                ["name","team","app","w_ip","w_era","w_whip","w_k9","w_bb9","w_hr9",
                 "r_era","r_whip","r_k9","r_bb9","r_hr9",
                 "d_era","d_whip","d_k9","d_bb9","d_hr9"],
            )
            continue
        if result == "filter":
            new_sf, new_tf, new_ip, _ = _filter_prompt(
                watched, season_filter, team_filter, ip_min=ip_min, show_ip=True
            )
            if (new_sf, new_tf, new_ip) != (season_filter, team_filter, ip_min):
                season_filter, team_filter, ip_min = new_sf, new_tf, new_ip
                need_ref_fetch = True
            continue
        if isinstance(result, tuple) and result[0] == "limit":
            limit, from_tail = _ask_limit(limit, result[1] == "t")
            continue
        if result is False:
            continue
        sort_col, sort_rev = result


def _show_comp_batting(watched: dict):
    season_filter: str | None = None
    team_filter:   str | None = None
    pa_min:        int | None = None
    sort_col, sort_rev = "_w_ops", True
    limit, from_tail   = 25, False

    # ── Step 1: ask for filters BEFORE any expensive fetching ────────────────
    clear()
    print_header("Small Sample — Batters")
    print("\n  Set filters before loading (reduces players fetched).\n")
    print(f"  Watched games: {len(watched)}")
    print(f"  Tip: set a Team filter to load only ~15-25 players instead of hundreds.\n")
    season_filter, team_filter, _, pa_min = _filter_prompt(
        watched, season_filter, team_filter, pa_min=pa_min, show_pa=True
    )

    # ── Step 2: fetch boxscore data once ─────────────────────────────────────
    clear()
    print_header("Small Sample — Batters")
    print(f"\n  Fetching boxscore data for {len(watched)} game(s)...\n")
    try:
        all_pitchers, all_batters = player_summary.collect_player_game_stats(watched)
    except Exception as e:
        print(f"\n  Error: {e}")
        input("\nPress Enter to continue...")
        return

    need_ref_fetch = True
    rows: list = []

    while True:
        if need_ref_fetch:
            _, batters_raw = player_summary.filter_and_aggregate(
                all_pitchers, all_batters,
                season_filter=season_filter,
                team_filter=team_filter,
            )
            ref_type = f"{season_filter} season" if season_filter else "career"
            leaderboard_size = len(player_summary.batting_leaderboard(batters_raw, pa_min=pa_min))

            clear()
            print_header("Small Sample — Batters")
            fl = _filters_label(season_filter, team_filter, pa_min=pa_min)
            print(f"\n  Fetching {ref_type} ref stats for {leaderboard_size} batters{fl}...\n")
            rows = comparison.build_batter_rows(batters_raw, pa_min=pa_min, season_filter=season_filter)
            need_ref_fetch = False

        try:
            sorted_rows = sorted(
                rows,
                key=lambda r: (float(r[sort_col].lstrip("▲▼ +-")) if isinstance(r[sort_col], str) and r[sort_col] not in ("—", "")
                               else r[sort_col] if isinstance(r[sort_col], (int, float)) else r[sort_col].lower()),
                reverse=sort_rev,
            )
        except Exception:
            sorted_rows = rows

        visible = _apply_limit(sorted_rows, limit, from_tail)

        clear()
        print_header("Small Sample — Batters")
        sort_label = next(l for l, k, _ in _COMP_BAT_SORT_COLS if k == sort_col)
        fl = _filters_label(season_filter, team_filter, pa_min=pa_min)
        print(f"\n  {len(rows)} batters  |  ref: {ref_type}  |  sorted by {sort_label}  |  showing {_limit_label(limit, from_tail)}{fl}\n")

        if not rows:
            print("  No batters match current filters.")
        else:
            n = "{:<22}  {:<18}  {:>4}  {:>5}  {:>5}"
            s = "  {:>6}  {:>5}  {:>5}  {:>5}"
            print("  " + n.format("Name", "Team", "App", "PA", "AB") + s.format("AVG", "OBP", "SLG", "OPS"))
            print("  " + "-"*22 + "  " + "-"*18 + "  " + "-"*4 + "  " + "-"*5 + "  " + "-"*5 + ("  " + "-"*6)*4)
            for r in visible:
                base = n.format(r["name"][:22], r["team"][:18], r["app"], r["w_pa"], r["w_ab"])
                print("  " + base + s.format(r["w_avg"], r["w_obp"], r["w_slg"], r["w_ops"]) + "  ← watched")
                print("  " + " "*52 + s.format(r["r_avg"], r["r_obp"], r["r_slg"], r["r_ops"]) + f"  ← {ref_type}")
                print("  " + " "*52 + s.format(r["d_avg"], r["d_obp"], r["d_slg"], r["d_ops"]) + "  ← delta")
                print()

        result = _sort_prompt(_COMP_BAT_SORT_COLS)
        if result is None:
            return
        if result == "csv":
            _dump_csv(
                "comp_batter.csv",
                ["Name","Team","App","W-PA","W-AB","W-AVG","W-OBP","W-SLG","W-OPS",
                 "R-AVG","R-OBP","R-SLG","R-OPS",
                 "D-AVG","D-OBP","D-SLG","D-OPS"],
                visible,
                ["name","team","app","w_pa","w_ab","w_avg","w_obp","w_slg","w_ops",
                 "r_avg","r_obp","r_slg","r_ops",
                 "d_avg","d_obp","d_slg","d_ops"],
            )
            continue
        if result == "filter":
            new_sf, new_tf, _, new_pa = _filter_prompt(
                watched, season_filter, team_filter, pa_min=pa_min, show_pa=True
            )
            if (new_sf, new_tf, new_pa) != (season_filter, team_filter, pa_min):
                season_filter, team_filter, pa_min = new_sf, new_tf, new_pa
                need_ref_fetch = True
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
        print("  [6]  My Small Sample")
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
        elif cmd == "6":
            screen_small_sample(watched)
        elif cmd == "q":
            print("\nBye!\n")
            break


if __name__ == "__main__":
    main()
