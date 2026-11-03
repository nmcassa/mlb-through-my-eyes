from __future__ import annotations


SEASON_TYPE_LABELS = {
    "preseason": "Preseason",
    "regular": "Regular season",
    "postseason": "Postseason",
    "unknown": "Unknown / legacy",
}


def normalize_mlb(code) -> str:
    value = str(code or "").upper()
    if value == "S":
        return "preseason"
    if value == "R":
        return "regular"
    if value in {"F", "D", "L", "W"}:
        return "postseason"
    return "unknown"


def normalize_espn(code, postseason_context: bool = False) -> str:
    value = str(code or "")
    if value == "1":
        return "preseason"
    if value == "2":
        return "regular"
    if value == "3" or postseason_context and value in {"4", "5"}:
        return "postseason"
    return "unknown"


def record_type(game: dict) -> str:
    value = game.get("season_type")
    return value if value in SEASON_TYPE_LABELS else "unknown"


def resolve_record_types(games: list[dict], fetcher) -> int:
    unresolved_by_date = {}
    for game in games:
        if record_type(game) == "unknown":
            unresolved_by_date.setdefault(game["date"], []).append(game)

    updated = 0
    for date, unresolved in unresolved_by_date.items():
        try:
            fetched = fetcher(date)
        except RuntimeError:
            continue
        fetched_by_id = {str(game["game_id"]): game for game in fetched}
        for game in unresolved:
            current = fetched_by_id.get(str(game["game_id"]))
            if current is None or record_type(current) == "unknown":
                continue
            game["season_type"] = current["season_type"]
            game["season_type_code"] = current.get("season_type_code")
            updated += 1
    return updated
