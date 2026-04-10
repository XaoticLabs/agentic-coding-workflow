#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
PreToolUse Hook: Python Toolchain Gate

Blocks wrong Python toolchain commands and tells Claude the correct tool.
Only activates in Python projects (pyproject.toml or setup.py present).

Enforces:
  - uv add/remove instead of pip install/uninstall
  - ruff format instead of black
  - ruff check instead of flake8/pylint/isort
  - basedpyright instead of mypy
  - uv run python instead of bare python/python3
"""

import json
import os
import re
import sys

# (pattern on command, correct tool, message)
TOOLCHAIN_BLOCKS = [
    (
        r"\bpip3?\s+install\b",
        "uv add <package>",
        "Use `uv add` instead of pip install",
    ),
    (
        r"\bpip3?\s+uninstall\b",
        "uv remove <package>",
        "Use `uv remove` instead of pip uninstall",
    ),
    (
        r"(?:^|[\s;&|])black\s",
        "uv run ruff format",
        "Use `uv run ruff format` instead of black",
    ),
    (
        r"(?:^|[\s;&|])flake8\b",
        "uv run ruff check",
        "Use `uv run ruff check` instead of flake8",
    ),
    (
        r"(?:^|[\s;&|])pylint\b",
        "uv run ruff check",
        "Use `uv run ruff check` instead of pylint",
    ),
    (
        r"(?:^|[\s;&|])isort\b",
        "uv run ruff check --select I",
        "Use `uv run ruff check --select I` instead of isort",
    ),
    (
        r"(?:^|[\s;&|])mypy\b",
        "uv run basedpyright",
        "Use `uv run basedpyright` instead of mypy",
    ),
]


def is_python_project() -> bool:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    return os.path.isfile(
        os.path.join(project_dir, "pyproject.toml")
    ) or os.path.isfile(os.path.join(project_dir, "setup.py"))


def check_bare_python(command: str) -> str | None:
    """Detect bare python/python3 invocation without uv run prefix."""
    # Split on shell separators to check each sub-command independently
    parts = re.split(r"&&|\|\||;|\|", command)
    for part in parts:
        stripped = part.strip()
        # Skip env var assignments before the command
        # e.g. PYTHONPATH=. python foo.py
        tokens = stripped.split()
        cmd_start = 0
        for i, token in enumerate(tokens):
            if "=" in token and not token.startswith("-"):
                cmd_start = i + 1
            else:
                break
        effective = " ".join(tokens[cmd_start:]) if cmd_start < len(tokens) else ""

        if not re.match(r"python3?\s", effective):
            continue
        # Allow version checks
        if re.match(r"python3?\s+(-V|--version)", effective):
            continue
        return "Use `uv run python` instead of bare `python`/`python3`"
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    if not is_python_project():
        sys.exit(0)

    # Check explicit toolchain violations
    for pattern, replacement, message in TOOLCHAIN_BLOCKS:
        if re.search(pattern, command):
            print(
                f"BLOCKED: Wrong Python toolchain\n\n"
                f"{message}\n\n"
                f"Correct command: {replacement}\n"
                f"Project toolchain: uv + ruff + basedpyright + pytest",
                file=sys.stderr,
            )
            sys.exit(2)

    # Check bare python usage
    reason = check_bare_python(command)
    if reason:
        print(
            f"BLOCKED: Wrong Python toolchain\n\n"
            f"{reason}\n\n"
            f"Project toolchain uses uv for all Python execution.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
