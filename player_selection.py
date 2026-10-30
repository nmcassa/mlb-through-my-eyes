from __future__ import annotations


CANCEL_SELECTION = object()


def choose_players(options: list[dict]) -> list[str] | None | object:
    if not options:
        return None
    selected = {option["key"] for option in options}
    all_keys = set(selected)
    while True:
        print("\n  Players whose stats count in Player Summary")
        print("  All eligible players are selected by default.\n")
        for index, option in enumerate(options, 1):
            marker = "x" if option["key"] in selected else " "
            roles = f" — {', '.join(option['roles'])}" if option["roles"] else ""
            print(f"  [{index:>2}] [{marker}] {option['name']} — {option['team']}{roles}")
        print("\n  Toggle numbers  |  a=all  n=none  Enter=save  q=cancel")
        command = input("\n  > ").strip().lower()
        if command == "q":
            return CANCEL_SELECTION
        if command == "a":
            selected = set(all_keys)
            continue
        if command == "n":
            selected.clear()
            continue
        if not command:
            return None if selected == all_keys else sorted(selected)
        for token in command.replace(",", " ").split():
            if not token.isdigit():
                continue
            index = int(token) - 1
            if 0 <= index < len(options):
                key = options[index]["key"]
                if key in selected:
                    selected.remove(key)
                else:
                    selected.add(key)
