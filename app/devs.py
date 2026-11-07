"""Manage developer tokens from the command line, since the web page has no login.

python -m app.devs add "Name"
python -m app.devs list
python -m app.devs swaps "Name" off
"""
import argparse
import json
import sqlite3

from . import config, store


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
            "ZERODOG_URL": url,
            "ZERODOG_TOKEN": token,
        }
    }


def add(name: str) -> int:
    try:
        _, token = store.add_developer(name)
    except sqlite3.IntegrityError:
        print(f"{name} already has a token.")
        return 1
    print(f"Created {name}. This token is shown only once.\n")
    print("Add this to ~/.claude/settings.json on their machine:\n")
    print(json.dumps(claude_code_settings(token), indent=2))
    return 0


def show() -> int:
    for developer in store.list_developers():
        state = "on" if developer["swaps_allowed"] else "off"
        print(f"{developer['name']}: model swaps {state}")
    return 0


def swaps(name: str, state: str) -> int:
    if not store.set_swaps_allowed(name, state == "on"):
        print(f"No developer named {name}.")
        return 1
    print(f"Model swaps are {state} for {name}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage ZeroDog developer tokens.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add").add_argument("name")
    commands.add_parser("list")
    swap = commands.add_parser("swaps")
    swap.add_argument("name")
    swap.add_argument("state", choices=["on", "off"])
    args = parser.parse_args()

    store.init()
    if args.command == "add":
        return add(args.name)
    if args.command == "swaps":
        return swaps(args.name, args.state)
    return show()


if __name__ == "__main__":
    raise SystemExit(main())
