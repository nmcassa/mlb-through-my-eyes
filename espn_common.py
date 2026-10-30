from __future__ import annotations

from collections.abc import Callable

from season_types import normalize_espn


def get(requests_module, base: str, path: str, timeout: int, **params) -> dict:
    url = f"{base}/{path}"
    try:
        response = requests_module.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests_module.RequestException as exc:
        raise RuntimeError(f"ESPN API request failed ({url}): {exc}") from exc


def find_teams(getter: Callable[..., dict], query: str, limit: int) -> list[dict]:
    data = getter("teams", limit=limit)
    needle = query.lower()
    leagues = data.get("sports", [{}])[0].get("leagues", [{}])
    teams = leagues[0].get("teams", []) if leagues else []
    found = []
    for entry in teams:
        team = entry.get("team", {})
        haystack = " ".join(
            str(team.get(key, ""))
            for key in ("displayName", "shortDisplayName", "name", "location", "abbreviation")
        ).lower()
        if needle in haystack:
            found.append({
                "id": team.get("id"),
                "name": team.get("displayName", "?"),
                "abbreviation": team.get("abbreviation", "?"),
            })
    return found


def score_value(competitor: dict) -> str:
    score = competitor.get("score", "")
    if isinstance(score, dict):
        return str(score.get("displayValue") or score.get("value") or "")
    return str(score) if score not in (None, "") else ""


def event_team_ids(event: dict) -> dict:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    away = next((item for item in competitors if item.get("homeAway") == "away"), {})
    home = next((item for item in competitors if item.get("homeAway") == "home"), {})
    return {
        "away": away.get("team", {}).get("id"),
        "home": home.get("team", {}).get("id"),
    }


def _event_season_type_code(event: dict) -> str | None:
    for source in (event, (event.get("competitions") or [{}])[0]):
        value = source.get("seasonType") or source.get("season_type") or source.get("season")
        if isinstance(value, dict):
            value = value.get("id") or value.get("type") or value.get("value")
        if value not in (None, ""):
            return str(value)
    return None


def parse_schedule_event(
    event: dict,
    date_converter: Callable[[str], str],
    season_type_code: str | None = None,
    postseason_context: bool = False,
) -> dict:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    away = next((item for item in competitors if item.get("homeAway") == "away"), {})
    home = next((item for item in competitors if item.get("homeAway") == "home"), {})
    status = competition.get("status", {}).get("type", {})
    completed = bool(status.get("completed"))
    raw_code = str(season_type_code) if season_type_code is not None else _event_season_type_code(event)
    return {
        "game_id": event.get("id"),
        "game_date": date_converter(event.get("date") or ""),
        "away_name": away.get("team", {}).get("displayName", "?"),
        "home_name": home.get("team", {}).get("displayName", "?"),
        "away_score": score_value(away) if completed else "",
        "home_score": score_value(home) if completed else "",
        "status": status.get("shortDetail") or status.get("description") or "",
        "completed": completed,
        "season_type": normalize_espn(raw_code, postseason_context),
        "season_type_code": raw_code,
    }


def fetch_team_schedule(
    getter: Callable[..., dict],
    parser: Callable[[dict], dict],
    team_id: str,
    season: str,
    season_types: list[str] | None = None,
    probe_codes: tuple[str, ...] = (),
) -> list[dict]:
    requested = season_types if season_types is not None else ["2"]
    codes = list(requested)
    if "3" in codes:
        codes.extend(code for code in probe_codes if code not in codes)
    games = []
    seen_ids = set()
    for season_type in codes:
        try:
            data = getter(f"teams/{team_id}/schedule", season=season, seasontype=season_type)
        except RuntimeError:
            if season_type in requested:
                raise
            continue
        for event in data.get("events", []):
            game_id = event.get("id")
            if not game_id or game_id in seen_ids:
                continue
            seen_ids.add(game_id)
            games.append(parser(event, season_type, "3" in requested))
    games.sort(key=lambda game: game["game_date"])
    return games


def fetch_games_by_date(
    getter: Callable[..., dict],
    parser: Callable[[dict], dict],
    date: str,
    team_id: str | None = None,
    **params,
) -> list[dict]:
    data = getter("scoreboard", dates=date.replace("-", ""), **params)
    events = data.get("events", [])
    games = [parser(event) for event in events]
    if team_id is not None:
        wanted_id = str(team_id)
        events_by_id = {event.get("id"): event for event in events}
        games = [
            game for game in games
            if wanted_id in {
                str(value) for value in event_team_ids(events_by_id.get(game["game_id"], {})).values()
            }
        ]
    games.sort(key=lambda game: game["game_date"])
    return games
