"""
nfl_dates.py
Shared date/season helpers for the NFL and college football trackers.
Football seasons are conventionally named by the year they START in (e.g.
"the 2024 season" runs Sept 2024 through the Super Bowl in Feb 2025) —
unlike the NBA tracker's "2024-25" hyphenated label, so this is a separate,
simpler helper rather than reusing nba_dates.py.
"""
from __future__ import annotations

from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    _EASTERN = ZoneInfo("America/New_York")
except Exception:
    _EASTERN = None   # fall back to naive UTC-date slicing if tzdata isn't available


def season_label(date_str: str) -> str:
    """
    Turn a game date ('YYYY-MM-DD') into a football season label — the
    year the season STARTS in. Preseason/regular season run Aug-Dec;
    playoffs and the Super Bowl run into January/February of the next
    calendar year, so games from Jan/Feb count as the back half of the
    PREVIOUS year's season (e.g. a February 2025 Super Bowl is the "2024"
    season).
    """
    try:
        y, m, _ = date_str.split("-")
        y, m = int(y), int(m)
    except (ValueError, AttributeError):
        return date_str or "?"

    return str(y if m >= 7 else y - 1)


def espn_date_to_local(iso_str: str) -> str:
    """
    ESPN returns event timestamps in UTC. Convert to US Eastern time first
    (the common broadcast/scheduling reference) before taking the date part
    — same reasoning as nba_dates.espn_date_to_local().
    """
    if not iso_str:
        return ""
    try:
        s = iso_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(s)
        if _EASTERN is not None:
            dt_utc = dt_utc.astimezone(_EASTERN)
        return dt_utc.strftime("%Y-%m-%d")
    except ValueError:
        return iso_str[:10]
