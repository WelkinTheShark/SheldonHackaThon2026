"""Manage developer tokens from the command line. The page's Users section does the same.

python -m app.devs add "Name" --team Core --access team
python -m app.devs list
python -m app.devs access "Name" all
python -m app.devs team "Name" Core
python -m app.devs token "Name"
python -m app.devs password "Name"
python -m app.devs swaps "Name" off

Access is self (own calls), team (same team's calls) or all (everything, plus managing users).
"""
import argparse
import getpass
import json
import sqlite3

from . import access, config, store


def claude_code_settings(token: str) -> dict:
    url = config.settings.public_url.rstrip("/")
    return {
        "env": {
            "ANTHROPIC_BASE_URL": url,
            "ANTHROPIC_AUTH_TOKEN": token,
            "CLAUDE_CODE_GATEWAY_HINT_HEADERS": "1",
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_ENDPOINT": url,
            "OTEL_EXPORTER_OTLP_HEADERS": f"x-api-key={token}",
            "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "delta",
            "CAVEDAWG_URL": url,
            "CAVEDAWG_TOKEN": token,
        }
    }


def _print_token(name: str, token: str) -> None:
    print(f"This token for {name} is shown only once. Use it to sign in to the page.")
    print()
    print("For Claude Code, add this to ~/.claude/settings.json on their machine:")
    print()
    print(json.dumps(claude_code_settings(token), indent=2))


def add(name: str, team: str = "", level: str = "self") -> int:
    try:
        _, token = store.add_developer(name, team, level)
    except sqlite3.IntegrityError:
        print(f"{name} already has a token.")
        return 1
    print(f"Created {name} on team {team or '(none)'} with {level} access.")
    _print_token(name, token)
    return 0


def _find(name: str) -> dict | None:
    developer = next((d for d in store.list_developers() if d["name"] == name), None)
    if not developer:
        print(f"No developer named {name}.")
    return developer


def show() -> int:
    for developer in store.list_developers():
        state = "on" if developer["swaps_allowed"] else "off"
        team = developer["team"] or "no team"
        print(f"{developer['name']}: {team}, {developer['access']} access, model swaps {state}")
    return 0


def change(name: str, **fields) -> int:
    developer = _find(name)
    if not developer:
        return 1
    store.update_developer(developer["id"], **fields)
    print(f"Updated {name}: " + ", ".join(f"{key} {value}" for key, value in fields.items()))
    return 0


def token(name: str) -> int:
    developer = _find(name)
    if not developer:
        return 1
    _print_token(name, store.rotate_token(developer["id"]))
    print()
    print("The old token no longer works.")
    return 0


def password(name: str) -> int:
    developer = _find(name)
    if not developer:
        return 1
    new = getpass.getpass(f"New page password for {name}: ")
    if len(new) < config.PASSWORD_MIN_CHARS:
        print(f"Use at least {config.PASSWORD_MIN_CHARS} characters.")
        return 1
    if getpass.getpass("Type it again: ") != new:
        print("The passwords didn't match.")
        return 1
    store.set_password(developer["id"], new)
    print(f"{name} can now sign in to the page with a username and password.")
    return 0


def swaps(name: str, state: str) -> int:
    if not store.set_swaps_allowed(name, state == "on"):
        print(f"No developer named {name}.")
        return 1
    print(f"Model swaps are {state} for {name}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage CaveDawg developer tokens.")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("add")
    new.add_argument("name")
    new.add_argument("--team", default="")
    new.add_argument("--access", default="self", choices=access.LEVELS)
    commands.add_parser("list")
    level = commands.add_parser("access")
    level.add_argument("name")
    level.add_argument("level", choices=access.LEVELS)
    team = commands.add_parser("team")
    team.add_argument("name")
    team.add_argument("team")
    commands.add_parser("token").add_argument("name")
    commands.add_parser("password").add_argument("name")
    swap = commands.add_parser("swaps")
    swap.add_argument("name")
    swap.add_argument("state", choices=["on", "off"])
    args = parser.parse_args()

    store.init()
    if args.command == "add":
        return add(args.name, args.team, args.access)
    if args.command == "access":
        return change(args.name, access=args.level)
    if args.command == "team":
        return change(args.name, team=args.team)
    if args.command == "token":
        return token(args.name)
    if args.command == "password":
        return password(args.name)
    if args.command == "swaps":
        return swaps(args.name, args.state)
    return show()


if __name__ == "__main__":
    raise SystemExit(main())
