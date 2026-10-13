"""
nba_dates.py
Shared date/season helpers for the NBA tracker.
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
    Turn a game date ('YYYY-MM-DD') into an NBA season label like '2024-25'.

    NBA seasons span two calendar years (tip-off in October, Finals in
    June), so bucketing games by calendar year alone splits one real season
    into two — e.g. an October 2024 game and a March 2025 game are the same
    2024-25 season but used to get filed under different "seasons".

    Games from August onward count as the start of a season; games from
    January-July count as the back half of the previous year's season.
    """
    try:
        y, m, _ = date_str.split("-")
        y, m = int(y), int(m)
    except (ValueError, AttributeError):
        return date_str or "?"

    start_year = y if m >= 8 else y - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def espn_date_to_local(iso_str: str) -> str:
    """
    ESPN returns event timestamps in UTC (e.g. '2026-01-05T00:30Z'). A lot
    of NBA games tip off in the evening US time, which is already the next
    calendar day in UTC — slicing the date straight out of that string
    gives an off-by-one date for those games. Convert to US Eastern time
    first (the common reference the NBA/broadcasters use for scheduling)
    before taking the date part.
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
        return iso_str[:10]   # fallback to the old (occasionally off-by-one) behavior
