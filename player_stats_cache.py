from __future__ import annotations

import json
from pathlib import Path


PLAYER_SUMMARY_KEYS_FIELD = "player_summary_player_keys"


def selected_player_keys(game: dict) -> set[str] | None:
    value = game.get(PLAYER_SUMMARY_KEYS_FIELD)
    if value is None or not isinstance(value, list):
        return None
    return {str(key) for key in value}


class PlayerStatsCache:
    def __init__(self, path: Path, schema: int):
        self.path = path
        self.schema = schema
        self._loaded = False
        self._entries: dict[str, object] = {}

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            with self.path.open(encoding="utf-8") as cache_file:
                for line in cache_file:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("schema") == self.schema:
                        self._entries[entry["key"]] = entry["data"]
        except OSError:
            pass

    def get(self, key: str):
        self._load()
        return self._entries.get(key)

    def put(self, key: str, data):
        self._load()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"schema": self.schema, "key": key, "data": data}
        with self.path.open("a", encoding="utf-8") as cache_file:
            json.dump(entry, cache_file, ensure_ascii=False, separators=(",", ":"))
            cache_file.write("\n")
        self._entries[key] = data
