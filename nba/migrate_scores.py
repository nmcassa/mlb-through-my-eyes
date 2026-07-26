#!/usr/bin/env python3
"""
migrate_scores.py
One-time fix for watched_nba_games.json files saved before the score-parsing
bug fix in espn_nba.py. ESPN's score field comes back as a dict like
{"value": 112.0, "displayValue": "112"}, not a plain string — earlier
versions of this tool saved that dict as-is into away_score/home_score.
This walks the file and flattens any dict-shaped score down to its display
string, in place. Safe to run more than once (already-fixed entries are
left alone).

Usage:
    python3 migrate_scores.py
    python3 migrate_scores.py /path/to/watched_nba_games.json
"""
import json
import sys
from pathlib import Path


def _flatten(score):
    if isinstance(score, dict):
        return str(score.get("displayValue") or score.get("value") or "")
    return score


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("watched_nba_games.json")
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    with open(path) as f:
        raw_text = f.read()
    watched = json.loads(raw_text)

    fixed = 0
    for game in watched.values():
        for key in ("away_score", "home_score"):
            if key in game and isinstance(game[key], dict):
                game[key] = _flatten(game[key])
                fixed += 1

    if fixed:
        backup = path.with_suffix(path.suffix + ".bak")
        with open(backup, "w") as f:
            f.write(raw_text)   # preserve the original, unmodified, just in case
        with open(path, "w") as f:
            json.dump(watched, f, indent=2)
        print(f"Fixed {fixed} score field(s) across {len(watched)} game(s) in {path}.")
        print(f"(Your original file was backed up to {backup} before any changes.)")
    else:
        print(f"No dict-shaped scores found in {path} — nothing to fix.")


if __name__ == "__main__":
    main()
