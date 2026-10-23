#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import json_store
import mlb


COMMAND_PATTERN = re.compile(
    r"^(?:/add\s+)?(?P<team>.+?)\s+(?P<date>\d{4}-\d{2}-\d{2})(?:\s+(?P<number>\d+))?$",
    re.IGNORECASE,
)


def parse_command(text: str) -> tuple[str, str, int | None]:
    match = COMMAND_PATTERN.match(text.strip())
    if not match:
        raise ValueError("Send: /add TEAM YYYY-MM-DD\nExample: /add Braves 2026-07-04")
    date = match.group("date")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("The date must be valid and use YYYY-MM-DD.") from error
    number = match.group("number")
    return match.group("team").strip(), date, int(number) if number else None


def game_label(game: dict) -> str:
    score = ""
    if game.get("away_score", "") != "" and game.get("home_score", "") != "":
        score = f" ({game['away_score']}-{game['home_score']})"
    return f"{game['away_name']} @ {game['home_name']}{score}"


def matching_games(team: str, date: str) -> list[dict]:
    query = team.casefold()
    games = mlb.fetch_games_by_date(date)
    return [
        game
        for game in games
        if query in game["away_name"].casefold() or query in game["home_name"].casefold()
    ]


def add_game(team: str, date: str, number: int | None = None) -> str:
    games = matching_games(team, date)
    if not games:
        return f"No game found for {team} on {date}."
    if len(games) > 1 and number is None:
        choices = "\n".join(f"{index}. {game_label(game)}" for index, game in enumerate(games, 1))
        return f"Multiple games found:\n{choices}\n\nSend the command again with the number at the end."
    index = (number or 1) - 1
    if index < 0 or index >= len(games):
        return f"Choose a game number from 1 to {len(games)}."
    game = games[index]
    game_id = str(game["game_id"])
    watched = json_store.load_watched()
    if game_id in watched:
        return f"Already added: {date} {game_label(game)}"
    watched[game_id] = {
        "game_id": game["game_id"],
        "date": game["game_date"],
        "away": game["away_name"],
        "home": game["home_name"],
        "away_score": game.get("away_score", ""),
        "home_score": game.get("home_score", ""),
        "added_at": datetime.now().isoformat(),
    }
    json_store.save_watched(watched)
    return f"Added: {date} {game_label(game)}"


class TelegramBot:
    def __init__(self, token: str, allowed_chat_id: int):
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.allowed_chat_id = allowed_chat_id

    def request(self, method: str, values: dict | None = None) -> dict:
        data = urllib.parse.urlencode(values or {}).encode()
        request = urllib.request.Request(f"{self.base_url}/{method}", data=data)
        with urllib.request.urlopen(request, timeout=70) as response:
            payload = json.load(response)
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram request failed"))
        return payload

    def send(self, text: str) -> None:
        self.request("sendMessage", {"chat_id": self.allowed_chat_id, "text": text})

    def handle(self, update: dict) -> None:
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text")
        if chat_id != self.allowed_chat_id or not text:
            return
        if text.strip().lower() in {"/start", "/help"}:
            self.send("Send: /add TEAM YYYY-MM-DD\nExample: /add Braves 2026-07-04")
            return
        try:
            team, date, number = parse_command(text)
            self.send(add_game(team, date, number))
        except (RuntimeError, ValueError) as error:
            self.send(str(error))

    def run(self) -> None:
        offset = 0
        while True:
            try:
                payload = self.request("getUpdates", {"offset": offset, "timeout": 60})
                for update in payload["result"]:
                    offset = update["update_id"] + 1
                    self.handle(update)
            except (OSError, RuntimeError, urllib.error.URLError) as error:
                print(f"Telegram error: {error}")
                time.sleep(5)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID")
    if not token or not chat_id:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_ID.")
    try:
        allowed_chat_id = int(chat_id)
    except ValueError as error:
        raise SystemExit("TELEGRAM_ALLOWED_CHAT_ID must be an integer.") from error
    TelegramBot(token, allowed_chat_id).run()


if __name__ == "__main__":
    main()
