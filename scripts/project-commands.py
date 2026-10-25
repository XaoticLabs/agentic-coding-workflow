#!/usr/bin/env python3
"""Read or initialize project commands without interpreting Markdown or shell code."""

import argparse
import json
import sys
from pathlib import Path
from typing import cast

ACTIONS = ("build", "test", "lint", "format", "run")


class CommandArguments(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.operation: str = ""
        self.project_dir: Path = Path(".")
        self.action: str = ""
        self.defaults: list[str] = []


def load_commands(path: Path) -> dict[str, str | None]:
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    decoded = cast(object, json.loads(contents))
    if not isinstance(decoded, dict):
        raise ValueError("expected an object mapping actions to shell commands")
    commands: dict[str, str | None] = {}
    for action, command in cast(dict[str, object], decoded).items():
        if action not in ACTIONS:
            raise ValueError(f"unknown action: {action}")
        if command is not None and not isinstance(command, str):
            raise ValueError(f"{action} must be a string or null")
        if isinstance(command, str) and "\0" in command:
            raise ValueError(f"{action} must not contain NUL characters")
        commands[action] = command
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    reader = subparsers.add_parser("get")
    _ = reader.add_argument("project_dir", type=Path)
    _ = reader.add_argument("action", choices=ACTIONS)
    initializer = subparsers.add_parser("init")
    _ = initializer.add_argument("project_dir", type=Path)
    _ = initializer.add_argument("defaults", nargs=len(ACTIONS), metavar="COMMAND")
    args = parser.parse_args(namespace=CommandArguments())
    path = args.project_dir / ".claude" / "project-commands.json"
    try:
        commands = load_commands(path)
        if args.operation == "get":
            if args.action not in commands:
                return 1  # Missing values permit framework auto-detection.
            _ = sys.stdout.write(commands[args.action] or "")
        else:
            defaults: dict[str, str | None] = dict(
                zip(ACTIONS, (value or None for value in args.defaults))
            )
            defaults.update(commands)  # Preserve project overrides, including null.
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = path.write_text(json.dumps(defaults, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Error: {path}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
