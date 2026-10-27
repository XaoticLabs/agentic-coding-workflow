#!/usr/bin/env python3
"""Read, inspect, or initialize project commands without running shell code."""

import argparse
import json
import sys
from pathlib import Path
from typing import cast

ACTIONS = ("build", "test", "lint", "format", "run")
EXTRA_ACTIONS = (
    "install",
    "health",
    "logs",
    "deploy_status",
    "flag_status",
    "verify",
    "quick_check",
)


class CommandArguments(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.operation: str = ""
        self.project_dir: Path = Path(".")
        self.action: str = ""
        self.defaults: list[str] = []
        self.omit_empty: bool = False
        self.required: bool = False


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
        if action not in (*ACTIONS, *EXTRA_ACTIONS):
            raise ValueError(f"unknown action: {action}")
        if command is not None and not isinstance(command, str):
            raise ValueError(f"{action} must be a string or null")
        if isinstance(command, str) and "\0" in command:
            raise ValueError(f"{action} must not contain NUL characters")
        commands[action] = command
    return commands


def project_readiness(
    project: Path, commands: dict[str, str | None]
) -> dict[str, object]:
    """Report configuration coverage; configured commands have not been run."""
    languages: list[str] = []
    if any((project / marker).is_file() for marker in ("go.mod", "go.work")):
        languages.append("go")
    if any(
        (project / marker).is_file()
        for marker in ("pyproject.toml", "setup.py", "setup.cfg")
    ) or any(project.glob("requirements*.txt")):
        languages.append("python")
    if (project / "tsconfig.json").is_file():
        languages.append("typescript")
    elif (project / "package.json").is_file():
        languages.append("javascript/typescript")
    if (project / "mix.exs").is_file():
        languages.append("elixir")

    configured_file = (project / ".claude/project-commands.json").is_file()
    checks = {
        action: {
            "status": "unconfigured"
            if action not in commands
            else "configured"
            if commands[action]
            else "disabled",
            "command": commands.get(action),
        }
        for action in ("lint", "test")
    }
    if not configured_file and languages == ["elixir"]:
        status = "legacy_elixir"
    elif not configured_file and not languages:
        status = "not_applicable"
    elif any(check["status"] == "unconfigured" for check in checks.values()):
        status = "unconfigured"
    elif all(check["status"] == "disabled" for check in checks.values()):
        status = "disabled"
    else:
        status = "configured"
    return {
        "status": status,
        "project": str(project),
        "configuration": str(project / ".claude/project-commands.json"),
        "languages": languages,
        "checks": checks,
        "verification": "not_run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    reader = subparsers.add_parser("get")
    _ = reader.add_argument("project_dir", type=Path)
    _ = reader.add_argument("action", choices=(*ACTIONS, *EXTRA_ACTIONS))
    _ = reader.add_argument(
        "--required",
        action="store_true",
        help="reject missing commands for recognized/configured projects",
    )
    initializer = subparsers.add_parser("init")
    _ = initializer.add_argument("--omit-empty", action="store_true")
    _ = initializer.add_argument("project_dir", type=Path)
    _ = initializer.add_argument("defaults", nargs=len(ACTIONS), metavar="COMMAND")
    inspector = subparsers.add_parser(
        "readiness", help="report command configuration as JSON; never execute checks"
    )
    _ = inspector.add_argument("project_dir", type=Path)
    args = parser.parse_args(namespace=CommandArguments())
    path = args.project_dir / ".claude" / "project-commands.json"
    try:
        commands = load_commands(path)
        if args.operation == "get":
            if args.action not in commands:
                if args.required and project_readiness(args.project_dir, commands)[
                    "status"
                ] not in ("legacy_elixir", "not_applicable"):
                    raise ValueError(
                        f"{args.action} command is unconfigured. Select the project's existing CI/task command, or explicitly disable it with null when project policy permits."
                    )
                return 1  # Missing values permit framework auto-detection.
            _ = sys.stdout.write(commands[args.action] or "")
        elif args.operation == "readiness":
            if not args.project_dir.is_dir():
                raise ValueError(
                    "project directory does not exist or is not a directory"
                )
            report = project_readiness(args.project_dir.resolve(), commands)
            print(json.dumps(report, indent=2))
            return 1 if report["status"] == "unconfigured" else 0
        else:
            defaults: dict[str, str | None] = dict(
                zip(ACTIONS, (value or None for value in args.defaults))
            )
            if args.omit_empty:
                defaults = {
                    action: value for action, value in defaults.items() if value
                }
            defaults.update(commands)  # Preserve project overrides, including null.
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = path.write_text(json.dumps(defaults, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        if args.operation == "readiness":
            print(
                json.dumps(
                    {
                        "status": "invalid",
                        "configuration": str(path),
                        "verification": "not_run",
                        "error": str(error),
                    }
                )
            )
        print(f"Error: {path}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
