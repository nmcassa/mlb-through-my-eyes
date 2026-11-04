from __future__ import annotations


def watch_count(watched: dict, game_id: object) -> int:
    game_id = str(game_id)
    return sum(str(game.get("game_id")) == game_id for game in watched.values())


def next_watch_key(watched: dict, game_id: object) -> str:
    game_id = str(game_id)
    if game_id not in watched and watch_count(watched, game_id) == 0:
        return game_id
    occurrence = 2
    while f"{game_id}#{occurrence}" in watched:
        occurrence += 1
    return f"{game_id}#{occurrence}"
