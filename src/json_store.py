"""
json_store.py
Handles reading and writing the watched games JSON file.
"""
from __future__ import annotations

import json
import os

WATCHED_FILE = "watched_games.json"


def load_watched() -> dict:
    """Load the watched games dict from disk. Returns an empty dict if the file doesn't exist."""
    if os.path.exists(WATCHED_FILE):
        with open(WATCHED_FILE) as f:
            return json.load(f)
    return {}


def save_watched(data: dict) -> None:
    """Persist the watched games dict to disk."""
    with open(WATCHED_FILE, "w") as f:
        json.dump(data, f, indent=2)


def watched_file_path() -> str:
    """Return the absolute path to the watched games file."""
    return os.path.abspath(WATCHED_FILE)
