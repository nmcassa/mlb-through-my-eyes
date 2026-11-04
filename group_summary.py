from __future__ import annotations


def aggregate(games: list[dict], group_maps: dict[str, dict], default_league: str) -> list[dict]:
    groups: dict[str, dict] = {}
    for game in games:
        group_map = group_maps.get(game.get("league", default_league), {})
        away_score = int(game["away_score"])
        home_score = int(game["home_score"])
        for side, scored, allowed in (
            ("away", away_score, home_score),
            ("home", home_score, away_score),
        ):
            name = game.get(f"{side}_conference")
            if not name:
                team_id = str(game.get(f"{side}_team_id") or "")
                name = group_map.get(team_id) or group_map.get(game[side])
            if not name:
                continue
            row = groups.setdefault(name, {"name": name, "W": 0, "L": 0, "ps": 0, "pa": 0, "g": 0})
            row["g"] += 1
            row["ps"] += scored
            row["pa"] += allowed
            if scored > allowed:
                row["W"] += 1
            elif scored < allowed:
                row["L"] += 1
    rows = []
    for row in groups.values():
        decisions = row["W"] + row["L"]
        rows.append({
            **row,
            "pct": row["W"] / decisions if decisions else 0,
            "ppg": row["ps"] / row["g"] if row["g"] else 0,
        })
    return rows
