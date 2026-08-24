#!/usr/bin/env python3
"""
nfl_main.py
NFL & College Football Watched Games Tracker — entry point.

A standalone sibling to the MLB tracker, pulling from ESPN's hidden API
(see espn_nfl.py) instead of MLB-StatsAPI. Same shape: browse a team's
season and mark games you watched, then see summaries built ONLY from
those games.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

import espn_nfl
import espn_cfb
import nfl_dates
import nfl_player_summary as player_summary
import nfl_json_store as json_store


# ── League registry ────────────────────────────────────────────────────────────
# Two leagues share this tracker: NFL and college football. Every
# watched game is tagged with a "league" key ("nfl" or "college"); games
# saved before college support existed have no tag and are treated as "nfl"
# everywhere (game.get("league", "nfl")) for backward compatibility.

LEAGUES = {
    "nfl":     {"key": "nfl",     "label": "NFL",     "icon": "🏈", "module": espn_nfl},
    "college": {"key": "college", "label": "College",  "icon": "🎓", "module": espn_cfb},
}


def _league_icon(league_key: str | None) -> str:
    return LEAGUES.get(league_key or "nfl", LEAGUES["nfl"])["icon"]


def _choose_league() -> dict | None:
    """Prompt for NFL vs College Football. Returns a LEAGUES entry, or None if cancelled."""
    print("\n  Which league?")
    print("    [1] 🏈 NFL")
    print("    [2] 🎓 College (NCAA)")
    print("    [q] Cancel")
    cmd = input("\n  > ").strip().lower()
    if cmd == "1":
        return LEAGUES["nfl"]
    if cmd == "2":
        return LEAGUES["college"]
    return None


# ── Display helpers ───────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  🏈  {title}")
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
    """Pick a league, then a team + season, then page through games to mark as watched."""
    print_header("Browse Season")

    league = _choose_league()
    if league is None:
        return
    module = league["module"]

    team_query = input(f"\nEnter {league['label']} team name (e.g. Eagles, Georgia): ").strip()
    if not team_query:
        return

    try:
        results = module.find_teams(team_query)
    except RuntimeError as e:
        print(f"Error: {e}")
        input("\nPress Enter to continue...")
        return

    if not results:
        print("No team found. Try a different name.")
        input("\nPress Enter to continue...")
        return

    if len(results) > 1:
        print(f"\nMultiple teams found ({len(results)}):")
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

    season = input("\nEnter season year (the year it STARTS in — e.g. 2024 for the 2024 season): ").strip()
    if not season.isdigit():
        print("Invalid year.")
        input("\nPress Enter to continue...")
        return

    # Ask which season type(s) to include — the schedule endpoint only
    # returns one type per request, so postseason games are invisible
    # unless asked for explicitly.
    print("\n  Which part(s) of the season to include?\n")
    all_types = list(module.SEASON_TYPE_LABELS.items())  # [(code, label), ...]
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

    type_labels = ", ".join(module.SEASON_TYPE_LABELS.get(t, t) for t in season_types)
    print(f"\nFetching {team['name']} {season} schedule ({type_labels})...")
    try:
        games = module.fetch_team_schedule(team["id"], season, season_types=season_types)
    except RuntimeError as e:
        print(f"Error: {e}")
        input("\nPress Enter to continue...")
        return

    if not games:
        print("No games found for that team/season.")
        input("\nPress Enter to continue...")
        return

    _game_select_loop(games, watched, team["name"], season, league)


# ── Screen: Browse by Date ────────────────────────────────────────────────────

def browse_by_date(watched: dict):
    """Pick a league, a single date (optionally a team), then page through that day's games."""
    print_header("Browse by Date")

    league = _choose_league()
    if league is None:
        return
    module = league["module"]

    date = input("\nEnter date (YYYY-MM-DD): ").strip()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        print("Invalid date. Use YYYY-MM-DD, e.g. 2024-12-25.")
        input("\nPress Enter to continue...")
        return

    team_query = input(f"{league['label']} team name (optional, press Enter for all teams): ").strip()
    team = None
    if team_query:
        try:
            results = module.find_teams(team_query)
        except RuntimeError as e:
            print(f"Error: {e}")
            input("\nPress Enter to continue...")
            return
        if not results:
            print("No team found. Try a different name.")
            input("\nPress Enter to continue...")
            return
        if len(results) > 1:
            print(f"\nMultiple teams found ({len(results)}):")
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

    print(f"\nFetching games for {date}" + (f" ({team['name']})" if team else "") + "...")
    try:
        games = module.fetch_games_by_date(date, team_id=team["id"] if team else None)
    except RuntimeError as e:
        print(f"Error: {e}")
        input("\nPress Enter to continue...")
        return

    if not games:
        print(f"No games found on {date}" + (f" for {team['name']}" if team else "") + ".")
        input("\nPress Enter to continue...")
        return

    label = f"{team['name']} — {date}" if team else f"All Teams — {date}"
    _game_select_loop(games, watched, label, date, league)


def _game_select_loop(games: list, watched: dict, team_name: str, season: str, league: dict):
    """Paginated game list with toggle-to-watch."""
    page_size   = 15
    page        = 0
    total_pages = (len(games) - 1) // page_size + 1

    while True:
        clear()
        print_header(f"{league['icon']} {team_name} — {season} Season")

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
                        "league":     league["key"],
                        "added_at":   datetime.now().isoformat(),
                    }
                    json_store.save_watched(watched)
                    print(f"\n  ★ Added:   {game_label(game)}")
                    _show_boxscore(game, league)
                    continue
                json_store.save_watched(watched)
                input("  Press Enter to continue...")


def _show_boxscore(game: dict, league: dict):
    """Fetch and print a formatted boxscore for a just-added game — one
    table per tracked category (QB/Rushing/Receiving), per team."""
    clear()
    print_header(f"{league['icon']} {game_label(game)}")
    print(f"\n  Fetching boxscore...\n")
    try:
        data = league["module"].fetch_boxscore_data(game["game_id"])
    except RuntimeError as e:
        print(f"  Could not load boxscore: {e}")
        input("\n  Press Enter to continue...")
        return

    qb_col  = "  {:<22} {:>6} {:>6} {:>5} {:>5} {:>4} {:>4} {:>6}"
    qb_hdr  = qb_col.format("QB", "C/ATT", "YDS", "TD", "INT", "SK", "RTG", "QBR")
    ru_col  = "  {:<22} {:>4} {:>6} {:>4}"
    ru_hdr  = ru_col.format("Rushing", "CAR", "YDS", "TD")
    rc_col  = "  {:<22} {:>4} {:>6} {:>4} {:>4}"
    rc_hdr  = rc_col.format("Receiving", "REC", "YDS", "TD", "TGT")

    for side in ("away", "home"):
        side_data = data.get(side, {})
        print(f"\n  {side_data.get('team', '?')}")

        passing = list(side_data.get("passing", {}).values())
        if passing:
            passing.sort(key=lambda p: p["stats"].get("pass_yds", 0), reverse=True)
            print(qb_hdr)
            print("  " + "-" * (len(qb_hdr) - 2))
            for p in passing:
                s = p["stats"]
                print(qb_col.format(
                    p["name"][:22], f"{s.get('cmp',0)}/{s.get('att',0)}", s.get("pass_yds", 0),
                    s.get("pass_td", 0), s.get("int", 0), s.get("sacks", 0),
                    f"{s.get('rtg',0):.1f}", f"{s.get('qbr',0):.1f}",
                ))

        rushing = list(side_data.get("rushing", {}).values())
        if rushing:
            rushing.sort(key=lambda p: p["stats"].get("rush_yds", 0), reverse=True)
            print("\n" + ru_hdr)
            print("  " + "-" * (len(ru_hdr) - 2))
            for p in rushing:
                s = p["stats"]
                print(ru_col.format(p["name"][:22], s.get("car", 0), s.get("rush_yds", 0), s.get("rush_td", 0)))

        receiving = list(side_data.get("receiving", {}).values())
        if receiving:
            receiving.sort(key=lambda p: p["stats"].get("rec_yds", 0), reverse=True)
            print("\n" + rc_hdr)
            print("  " + "-" * (len(rc_hdr) - 2))
            for p in receiving:
                s = p["stats"]
                print(rc_col.format(
                    p["name"][:22], s.get("rec", 0), s.get("rec_yds", 0),
                    s.get("rec_td", 0), s.get("tgts", 0),
                ))

    input("\n  Press Enter to continue...")


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
        year = nfl_dates.season_label(g["date"])
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
            icon   = _league_icon(g.get("league"))
            print(f"    {icon} {g['date']}  {g['away']} @ {g['home']}{score}")
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
        icon   = _league_icon(g.get("league"))
        print(f"  [{i+1:>2}]  {icon} {g['date']}  {g['away']} @ {g['home']}{score}")

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

def _apply_watched_filters(
    watched: dict,
    season_filter: str | None,
    team_filter: str | None,
    league_filter: str | None = None,
) -> dict:
    """Return a subset of watched matching the active season/team/league filters."""
    out = {}
    for gid, g in watched.items():
        if season_filter and nfl_dates.season_label(g["date"]) != season_filter:
            continue
        if team_filter and team_filter not in (g["away"], g["home"]):
            continue
        if league_filter and g.get("league", "nfl") != league_filter:
            continue
        out[gid] = g
    return out


def _filters_label(
    season_filter: str | None,
    team_filter: str | None,
    min_min: float | None = None,
    league_filter: str | None = None,
) -> str:
    parts = []
    if season_filter:
        parts.append(f"season={season_filter}")
    if team_filter:
        parts.append(f"team={team_filter}")
    if league_filter:
        parts.append(f"league={LEAGUES[league_filter]['label']}")
    if min_min is not None:
        parts.append(f"min_volume≥{min_min:.0f}")
    return "  |  filters: " + ", ".join(parts) if parts else ""


def _filter_prompt(
    watched: dict,
    season_filter: str | None,
    team_filter: str | None,
    min_min: float | None = None,
    show_min: bool = False,
    league_filter: str | None = None,
) -> tuple:
    """Interactive filter menu. Returns (season_filter, team_filter, min_min, league_filter)."""
    while True:
        clear()
        print_header("Filters")
        print("\n  ── Active filters ──────────────────────────────")
        print(f"    League : {LEAGUES[league_filter]['label'] if league_filter else 'all'}")
        print(f"    Season : {season_filter or 'all'}")
        print(f"    Team   : {team_filter or 'all'}")
        if show_min:
            print(f"    Min volume: {min_min if min_min is not None else 'category default'}")

        print("\n  ── Change filter ───────────────────────────────")
        print("    [1] Season")
        print("    [2] Team  (players on that team only)")
        print("    [3] League  (NFL / College / both)")
        if show_min:
            print("    [4] Min volume  (attempts/carries/receptions, depending on category)")
        print("    [x] Clear all filters")
        print("    [q] Done")

        cmd = input("\n  > ").strip().lower()
        if cmd == "q":
            return season_filter, team_filter, min_min, league_filter
        if cmd == "x":
            season_filter, team_filter, min_min, league_filter = None, None, None, None
            continue
        if cmd == "1":
            seasons = sorted({nfl_dates.season_label(g["date"]) for g in watched.values()})
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
        if cmd == "3":
            print("\n    [1] NFL only")
            print("    [2] College only")
            print("    [3] Both (clear league filter)")
            sub = input("  > ").strip()
            if sub == "1":
                league_filter = "nfl"
            elif sub == "2":
                league_filter = "college"
            elif sub == "3":
                league_filter = None
            continue
        if cmd == "4" and show_min:
            raw = input("  Minimum volume — attempts (QB) / carries (Rushing) / receptions (Receiving); blank = category default: ").strip()
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
    league_filter: str | None = None

    sort_col, sort_rev = "pct", True
    page, page_size    = 0, 25

    while True:
        active = _apply_watched_filters(watched, season_filter, team_filter, league_filter)
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
        fl = _filters_label(season_filter, team_filter, league_filter=league_filter)
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
                "nfl_game_summary.csv",
                ["Team", "W", "L", "PCT", "PS", "PA", "G", "PTS/G"],
                csv_rows,
                ["name", "W", "L", "pct", "ps", "pa", "g", "ppg"],
            )
            continue
        if result == "filter":
            season_filter, team_filter, _, league_filter = _filter_prompt(
                watched, season_filter, team_filter, league_filter=league_filter
            )
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

_CATEGORY_LABELS = {"qb": "QB (Passing)", "rushing": "Rushing", "receiving": "Receiving"}
_CATEGORY_ICONS  = {"qb": "🎯", "rushing": "🏃", "receiving": "🙌"}

_SORT_COLS_QB = [
    ("Name", "name", False), ("Team", "team", False), ("Appearances", "app", True),
    ("QB+", "plus", True), ("FPPG", "_fppg", True),
    ("Comp%", "_cmp_pct", True), ("YDS/ATT", "_ypa", True), ("Pass YDS", "pass_yds", True),
    ("Pass TD", "pass_td", True), ("INT", "int", False), ("YDS/G", "_ypg", True),
]
_SORT_COLS_RUSHING = [
    ("Name", "name", False), ("Team", "team", False), ("Appearances", "app", True),
    ("Rush+", "plus", True), ("FPPG", "_fppg", True),
    ("Carries", "car", True), ("Rush YDS", "rush_yds", True), ("YDS/Carry", "_ypc", True),
    ("Rush TD", "rush_td", True), ("YDS/G", "_ypg", True),
]
_SORT_COLS_RECEIVING = [
    ("Name", "name", False), ("Team", "team", False), ("Appearances", "app", True),
    ("Rec+", "plus", True), ("FPPG", "_fppg", True),
    ("Receptions", "rec", True), ("Targets", "tgts", True), ("Rec YDS", "rec_yds", True),
    ("YDS/Catch", "_ypc", True), ("Rec TD", "rec_td", True), ("YDS/G", "_ypg", True),
]
_CATEGORY_SORT_COLS = {"qb": _SORT_COLS_QB, "rushing": _SORT_COLS_RUSHING, "receiving": _SORT_COLS_RECEIVING}


def _choose_stat_category() -> str | None:
    """Prompt for QB / Rushing / Receiving. Returns the category key, or None if cancelled."""
    print("\n  Which stat category?")
    print("    [1] 🎯 QB (Passing)")
    print("    [2] 🏃 Rushing")
    print("    [3] 🙌 Receiving")
    print("    [q] Cancel")
    cmd = input("\n  > ").strip().lower()
    return {"1": "qb", "2": "rushing", "3": "receiving"}.get(cmd)


_PLUS_LABEL = {"qb": "QB+", "rushing": "Rush+", "receiving": "Rec+"}


def _print_player_row(category: str, r: dict):
    if category == "qb":
        col = "{:<20}  {:<3}  {:<18}  {:>4}  {:>5}  {:>6}  {:>6}  {:>7}  {:>9}  {:>7}  {:>4}  {:>6}"
        print("  " + col.format(
            r["name"][:20], _league_icon(r.get("league")), r["team"][:18], r["app"], r["plus_disp"], r["fppg"],
            r["cmp_pct"], r["ypa"], r["pass_yds"], r["pass_td"], r["int"], r["ypg"],
        ))
    elif category == "rushing":
        col = "{:<20}  {:<3}  {:<18}  {:>4}  {:>6}  {:>6}  {:>7}  {:>8}  {:>9}  {:>7}  {:>6}"
        print("  " + col.format(
            r["name"][:20], _league_icon(r.get("league")), r["team"][:18], r["app"], r["plus_disp"], r["fppg"],
            r["car"], r["rush_yds"], r["ypc"], r["rush_td"], r["ypg"],
        ))
    else:
        col = "{:<20}  {:<3}  {:<18}  {:>4}  {:>5}  {:>6}  {:>10}  {:>7}  {:>7}  {:>9}  {:>7}  {:>6}"
        print("  " + col.format(
            r["name"][:20], _league_icon(r.get("league")), r["team"][:18], r["app"], r["plus_disp"], r["fppg"],
            r["rec"], r["tgts"], r["rec_yds"], r["ypc"], r["rec_td"], r["ypg"],
        ))


def _player_col_header(category: str) -> str:
    if category == "qb":
        col = "{:<20}  {:<3}  {:<18}  {:>4}  {:>5}  {:>6}  {:>6}  {:>7}  {:>9}  {:>7}  {:>4}  {:>6}"
        return col.format("Name", "Lg", "Team", "App", "QB+", "FPPG", "Comp%", "YDS/AT", "Pass YDS", "Pass TD", "INT", "YDS/G")
    if category == "rushing":
        col = "{:<20}  {:<3}  {:<18}  {:>4}  {:>6}  {:>6}  {:>7}  {:>8}  {:>9}  {:>7}  {:>6}"
        return col.format("Name", "Lg", "Team", "App", "Rush+", "FPPG", "Carries", "Rush YDS", "YDS/Car", "Rush TD", "YDS/G")
    col = "{:<20}  {:<3}  {:<18}  {:>4}  {:>5}  {:>6}  {:>10}  {:>7}  {:>7}  {:>9}  {:>7}  {:>6}"
    return col.format("Name", "Lg", "Team", "App", "Rec+", "FPPG", "Receptions", "Targets", "Rec YDS", "YDS/Cat", "Rec TD", "YDS/G")


_CSV_FIELDS = {
    "qb": (["Name", "League", "Team", "App", "QB+", "FPPG", "Comp%", "YDS/ATT", "Pass YDS", "Pass TD", "INT", "Sacks", "YDS/G"],
           ["name", "league", "team", "app", "plus_disp", "fppg", "cmp_pct", "ypa", "pass_yds", "pass_td", "int", "sacks", "ypg"]),
    "rushing": (["Name", "League", "Team", "App", "Rush+", "FPPG", "Carries", "Rush YDS", "YDS/Carry", "Rush TD", "YDS/G"],
                ["name", "league", "team", "app", "plus_disp", "fppg", "car", "rush_yds", "ypc", "rush_td", "ypg"]),
    "receiving": (["Name", "League", "Team", "App", "Rec+", "FPPG", "Receptions", "Targets", "Rec YDS", "YDS/Catch", "Rec TD", "YDS/G"],
                  ["name", "league", "team", "app", "plus_disp", "fppg", "rec", "tgts", "rec_yds", "ypc", "rec_td", "ypg"]),
}


def _show_players(watched: dict):
    category = _choose_stat_category()
    if category is None:
        return
    cat_label = _CATEGORY_LABELS[category]

    season_filter: str | None = None
    team_filter:   str | None = None
    min_min:       float | None = None   # min attempts/carries/receptions to qualify
    league_filter: str | None = None

    sort_cols = _CATEGORY_SORT_COLS[category]
    sort_col, sort_rev = sort_cols[2][1], True   # default: sort by Appearances
    page, page_size    = 0, 25

    # ── Step 1: ask for filters BEFORE any expensive fetching ────────────────
    clear()
    print_header(f"Player Summary — {cat_label}")
    print("\n  Set filters before loading (reduces games fetched).\n")
    print(f"  Watched games: {len(watched)}\n")
    season_filter, team_filter, min_min, league_filter = _filter_prompt(
        watched, season_filter, team_filter, min_min=min_min, show_min=True, league_filter=league_filter
    )

    fetch_watched = _apply_watched_filters(watched, season_filter, team_filter, league_filter)
    clear()
    print_header(f"Player Summary — {cat_label}")
    print(f"\n  Fetching box score data for {len(fetch_watched)} game(s) (filtered from {len(watched)} total)...\n")
    try:
        all_pools = player_summary.collect_player_game_stats(fetch_watched)
    except Exception as e:
        print(f"\n  Error collecting stats: {e}")
        input("\nPress Enter to continue...")
        return

    while True:
        pool = all_pools[category]
        players_raw = player_summary.filter_and_aggregate(
            pool,
            season_filter=None,          # already applied at fetch time
            team_filter=team_filter,     # still needed to exclude opponents
            league_filter=league_filter, # still needed to exclude opponents' league mismatches
            category=category,
        )
        rows = player_summary.player_leaderboard(players_raw, category, min_volume=min_min)
        player_summary.annotate_plus(rows, category)   # pool = this qualifying leaderboard

        sorted_rows = _sort_rows(rows, sort_col, sort_rev)
        visible, page, total_pages = _paginate(sorted_rows, page, page_size)

        clear()
        print_header(f"Player Summary — {cat_label}")
        sort_label = next(l for l, k, _ in sort_cols if k == sort_col)
        fl = _filters_label(season_filter, team_filter, min_min=min_min, league_filter=league_filter)
        print(f"\n  {len(rows)} players  |  sorted by {sort_label}  |  {_page_label(page, total_pages)}{fl}\n")
        print(f"  {_PLUS_LABEL[category]}: 100 = average of these players, weighted by volume. Higher is better.")
        print(f"  Only players with {cat_label.lower()} stats appear here.\n")

        if not rows:
            print("  No players match current filters.")
        else:
            print("  " + _player_col_header(category))
            print("  " + "-" * (len(_player_col_header(category)) + 2))
            for r in visible:
                _print_player_row(category, r)
            if total_pages > 1:
                print(f"\n  Press [n]/[p] to scroll pages.")

        result = _sort_prompt(sort_cols, total_pages)
        if result is None:
            return
        if result == "csv":
            headers, fields = _CSV_FIELDS[category]
            _dump_csv(f"nfl_{category}_summary.csv", headers, visible, fields)
            continue
        if result == "filter":
            new_sf, new_tf, new_min, new_lf = _filter_prompt(
                watched, season_filter, team_filter, min_min=min_min, show_min=True, league_filter=league_filter
            )
            if (new_sf, new_tf, new_lf) != (season_filter, team_filter, league_filter):
                season_filter, team_filter, min_min, league_filter = new_sf, new_tf, new_min, new_lf
                fetch_watched = _apply_watched_filters(watched, season_filter, team_filter, league_filter)
                clear()
                print_header(f"Player Summary — {cat_label}")
                print(f"\n  Re-fetching box score data for {len(fetch_watched)} game(s)...\n")
                try:
                    all_pools = player_summary.collect_player_game_stats(fetch_watched)
                except Exception as e:
                    print(f"\n  Error: {e}")
                    input("\nPress Enter to continue...")
                    return
            else:
                season_filter, team_filter, min_min, league_filter = new_sf, new_tf, new_min, new_lf
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
            all_pools = player_summary.collect_player_game_stats(watched)
        except Exception as e:
            print(f"\n  Error collecting stats: {e}")
            input("\nPress Enter to continue...")
            return

        q = query.lower()
        all_names = set()
        for pool in all_pools.values():
            all_names.update(pool.keys())
        matches = sorted(n for n in all_names if q in n.lower())

        if not matches:
            print(f"\n  No players matching '{query}' found in your watched games (with QB/rushing/receiving stats).")
            input("\nPress Enter to continue...")
            continue

        # Plus-score baselines: everyone qualifying across your ENTIRE
        # watched history in each category, so a player's score means
        # "compared to everyone you've watched" consistently.
        baselines = {}
        for category in ("qb", "rushing", "receiving"):
            pool_raw  = player_summary.filter_and_aggregate(all_pools[category], category=category)
            pool_rows = player_summary.player_leaderboard(pool_raw, category)
            baselines[category] = player_summary.compute_pool_baseline(category, pool_rows)

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

        _show_player_seasons(name, all_pools, baselines)


def _show_player_seasons(name: str, all_pools: dict, baselines: dict):
    """Render a per-season table for one player, one section per stat
    category (QB / Rushing / Receiving) they have games in — a dual-threat
    player can appear in more than one section."""
    while True:
        clear()
        print_header(f"Season Log — {name}")

        any_rows = False
        rows_by_category = {}
        for category in ("qb", "rushing", "receiving"):
            player_data = all_pools[category].get(name)
            rows = player_summary.player_season_rows(name, player_data["games"], category) if player_data else []
            for r in rows:
                p = player_summary.plus_score(category, r, baselines.get(category))
                r["plus"], r["plus_disp"] = p, (str(p) if p is not None else "—")
            rows_by_category[category] = rows
            if rows:
                any_rows = True

        if not any_rows:
            print("\n  No qualifying games found for this player.")
        else:
            for category in ("qb", "rushing", "receiving"):
                rows = rows_by_category[category]
                if not rows:
                    continue
                print(f"\n  {_CATEGORY_ICONS[category]} {_CATEGORY_LABELS[category]}   "
                      f"({_PLUS_LABEL[category]}: 100 = avg of everyone you've watched)\n")
                print("  " + _season_col_header(category))
                print("  " + "-" * (len(_season_col_header(category)) + 2))
                for r in rows:
                    icon = "🌐" if r.get("league") == "ALL" else _league_icon(r.get("league"))
                    _print_season_row(category, r, icon)

        print("\n  [c] Export to CSV")
        print("  [q] Back")
        cmd = input("\n  > ").strip().lower()
        if cmd == "q":
            return
        if cmd == "c" and any_rows:
            safe_name = name.replace(" ", "_").replace("/", "_")
            for category in ("qb", "rushing", "receiving"):
                rows = rows_by_category[category]
                if not rows:
                    continue
                headers, fields = _CSV_FIELDS[category]
                headers = ["Season"] + headers[1:]   # swap Name for Season as the leading column
                fields  = ["season"] + fields[1:]
                _dump_csv(f"{safe_name}_{category}_by_season.csv", headers, rows, fields)


def _season_col_header(category: str) -> str:
    if category == "qb":
        col = "{:<16}  {:<3}  {:<18}  {:>4}  {:>5}  {:>6}  {:>6}  {:>7}  {:>9}  {:>7}  {:>4}  {:>6}"
        return col.format("Season", "Lg", "Team", "App", "QB+", "FPPG", "Comp%", "YDS/AT", "Pass YDS", "Pass TD", "INT", "YDS/G")
    if category == "rushing":
        col = "{:<16}  {:<3}  {:<18}  {:>4}  {:>6}  {:>6}  {:>7}  {:>8}  {:>9}  {:>7}  {:>6}"
        return col.format("Season", "Lg", "Team", "App", "Rush+", "FPPG", "Carries", "Rush YDS", "YDS/Car", "Rush TD", "YDS/G")
    col = "{:<16}  {:<3}  {:<18}  {:>4}  {:>5}  {:>6}  {:>10}  {:>7}  {:>7}  {:>9}  {:>7}  {:>6}"
    return col.format("Season", "Lg", "Team", "App", "Rec+", "FPPG", "Receptions", "Targets", "Rec YDS", "YDS/Cat", "Rec TD", "YDS/G")


def _print_season_row(category: str, r: dict, icon: str):
    if category == "qb":
        col = "{:<16}  {:<3}  {:<18}  {:>4}  {:>5}  {:>6}  {:>6}  {:>7}  {:>9}  {:>7}  {:>4}  {:>6}"
        print("  " + col.format(
            r["season"], icon, r["team"][:18], r["app"], r["plus_disp"], r["fppg"],
            r["cmp_pct"], r["ypa"], r["pass_yds"], r["pass_td"], r["int"], r["ypg"],
        ))
    elif category == "rushing":
        col = "{:<16}  {:<3}  {:<18}  {:>4}  {:>6}  {:>6}  {:>7}  {:>8}  {:>9}  {:>7}  {:>6}"
        print("  " + col.format(
            r["season"], icon, r["team"][:18], r["app"], r["plus_disp"], r["fppg"],
            r["car"], r["rush_yds"], r["ypc"], r["rush_td"], r["ypg"],
        ))
    else:
        col = "{:<16}  {:<3}  {:<18}  {:>4}  {:>5}  {:>6}  {:>10}  {:>7}  {:>7}  {:>9}  {:>7}  {:>6}"
        print("  " + col.format(
            r["season"], icon, r["team"][:18], r["app"], r["plus_disp"], r["fppg"],
            r["rec"], r["tgts"], r["rec_yds"], r["ypc"], r["rec_td"], r["ypg"],
        ))


# ── Main menu ─────────────────────────────────────────────────────────────────

def main():
    watched = json_store.load_watched()

    while True:
        watched = json_store.load_watched()
        clear()
        print_header("NFL & CFB Watched Games Tracker")
        print(f"\n  {len(watched)} game(s) watched  |  file: {json_store.watched_file_path()}\n")
        print("  [1]  Browse a season & mark games watched")
        print("  [2]  View all watched games")
        print("  [3]  Remove a watched game")
        print("  [4]  Game Summary")
        print("  [5]  Player Summary")
        print("  [6]  Search Player")
        print("  [7]  Browse by Date")
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
        elif cmd == "7":
            browse_by_date(watched)
        elif cmd == "q":
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
