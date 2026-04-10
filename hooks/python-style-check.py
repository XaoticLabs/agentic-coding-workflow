#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
PostToolUse Hook: Python Style Check

Runs after every Edit/Write on .py files. Checks the new code against
project Python conventions and outputs warnings that Claude sees as
conversation feedback — forcing immediate correction rather than hoping
the agent remembers every rule.

Only activates in Python projects (pyproject.toml or setup.py present).
"""

import json
import os
import re
import sys


def is_python_project() -> bool:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    return os.path.isfile(
        os.path.join(project_dir, "pyproject.toml")
    ) or os.path.isfile(os.path.join(project_dir, "setup.py"))


def is_test_file(file_path: str) -> bool:
    basename = os.path.basename(file_path)
    return (
        basename.startswith("test_")
        or basename.endswith("_test.py")
        or "/tests/" in file_path
        or "/test/" in file_path
        or file_path.startswith("tests/")
        or file_path.startswith("test/")
        or "conftest" in basename
    )


# ── Patterns checked in all Python files ────────────────────────────

ALWAYS_CHECK = [
    (
        r"@staticmethod",
        "`@staticmethod` — use a module-level function instead (never @staticmethod)",
    ),
    (
        r"logger\.\w+\(f[\"']",
        "f-string in logger call — use %-style: `logger.info(\"User %s\", name)`",
    ),
    (
        r"logging\.\w+\(f[\"']",
        "f-string in logging call — use %-style: `logging.info(\"User %s\", name)`",
    ),
    (
        r"\.dict\(\)",
        "Pydantic v1 API `.dict()` — use `.model_dump()` instead",
    ),
    (
        r"\.parse_obj\(",
        "Pydantic v1 API `.parse_obj()` — use `.model_validate()` instead",
    ),
    (
        r"\.parse_raw\(",
        "Pydantic v1 API `.parse_raw()` — use `.model_validate_json()` instead",
    ),
    (
        r"from\s+pydantic\s+import\s+validator\b",
        "Pydantic v1 `validator` — use `field_validator` instead",
    ),
    (
        r"class\s+Config\s*:",
        "Pydantic v1 `class Config:` — use `model_config = ConfigDict(...)` instead",
    ),
    (
        r"@property\s*\n\s*def\s+\w+\(self\)\s*.*:\s*\n\s*return\s+self\._\w+\s*$",
        "`@property` wrapping a trivial private attr — expose the attribute directly",
    ),
]

# ── Patterns only checked outside test files ────────────────────────

NON_TEST_CHECK = [
    (
        r"^\s*assert\s+(?!.*#\s*type:)",
        "`assert` outside tests — stripped with `-O`. Use `raise` or pydantic validation",
    ),
]

# ── Patterns that need the full file (Write only) ──────────────────

def check_function_length(content: str) -> list[str]:
    """Find functions longer than 40 lines."""
    warnings = []
    lines = content.split("\n")
    func_start = None
    func_name = None
    func_indent = 0

    for i, line in enumerate(lines):
        # Detect function definition
        match = re.match(r"^(\s*)(async\s+)?def\s+(\w+)", line)
        if match:
            # If we were tracking a function, check its length
            if func_start is not None:
                length = i - func_start
                if length > 40:
                    warnings.append(
                        f"`{func_name}` is {length} lines (limit: 40) — break it up"
                    )
            func_indent = len(match.group(1))
            func_name = match.group(3)
            func_start = i
            continue

        # Check if we've exited the current function (dedent to same or less)
        if func_start is not None and line.strip():
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= func_indent and not line.strip().startswith((")", "]", "}")):
                length = i - func_start
                if length > 40:
                    warnings.append(
                        f"`{func_name}` is {length} lines (limit: 40) — break it up"
                    )
                func_start = None

    # Check last function in file
    if func_start is not None:
        length = len(lines) - func_start
        if length > 40:
            warnings.append(
                f"`{func_name}` is {length} lines (limit: 40) — break it up"
            )

    return warnings


def check_code(code: str, file_path: str, is_full_file: bool) -> list[str]:
    """Run all applicable checks on the code."""
    warnings = []

    for pattern, message in ALWAYS_CHECK:
        if re.search(pattern, code, re.MULTILINE):
            warnings.append(message)

    if not is_test_file(file_path):
        for pattern, message in NON_TEST_CHECK:
            if re.search(pattern, code, re.MULTILINE):
                warnings.append(message)

    # Function length check only makes sense with the full file
    if is_full_file:
        warnings.extend(check_function_length(code))

    return warnings


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path.endswith(".py"):
        sys.exit(0)

    if not is_python_project():
        sys.exit(0)

    # Get the code to check
    if tool_name == "Edit":
        code = tool_input.get("new_string", "")
        is_full_file = False
    else:  # Write
        code = tool_input.get("content", "")
        is_full_file = True

    if not code:
        sys.exit(0)

    warnings = check_code(code, file_path, is_full_file)

    if warnings:
        basename = os.path.basename(file_path)
        print(f"Python style violations in {basename}:")
        for w in warnings:
            print(f"  - {w}")
        print(f"\nFix before continuing (see .claude/rules/python.md)")

    sys.exit(0)


if __name__ == "__main__":
    main()
