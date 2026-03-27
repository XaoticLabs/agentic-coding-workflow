#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Stop Hook: Output Validator

Validates that commands/skills produced the expected output before allowing
Claude to stop. Commands write their expectations to .claude/expected-output.json
at the start of execution. This hook reads that file on Stop, validates each
rule, and blocks if requirements aren't met.

Expected format of .claude/expected-output.json:
{
    "source": "plan",
    "rules": [
        {
            "type": "file_exists",
            "path": ".claude/plans/my-plan.md"
        },
        {
            "type": "file_contains",
            "path": ".claude/plans/my-plan.md",
            "sections": ["## Objective", "## Tasks", "## Success Criteria"]
        },
        {
            "type": "file_min_lines",
            "path": ".claude/plans/my-plan.md",
            "min_lines": 20
        },
        {
            "type": "dir_files_contain",
            "path": ".claude/specs/my-feature/",
            "glob": "*.md",
            "exclude": ["IMPLEMENTATION_PLAN.md"],
            "sections": ["## Acceptance Criteria"],
            "min_files": 1
        }
    ]
}
"""

import glob as glob_mod
import json
import os
import sys
from pathlib import Path


def validate_file_exists(rule: dict, project_dir: str) -> tuple[bool, str]:
    """Check that a file exists."""
    path = os.path.join(project_dir, rule["path"])
    if os.path.isfile(path):
        return True, ""
    return False, f"Expected output file does not exist: {rule['path']}"


def validate_file_contains(rule: dict, project_dir: str) -> tuple[bool, str]:
    """Check that a file contains required sections/strings."""
    path = os.path.join(project_dir, rule["path"])
    if not os.path.isfile(path):
        return False, f"Cannot validate contents — file does not exist: {rule['path']}"

    try:
        content = Path(path).read_text()
    except Exception as e:
        return False, f"Cannot read {rule['path']}: {e}"

    missing = []
    for section in rule.get("sections", []):
        if section not in content:
            missing.append(section)

    if missing:
        return False, (
            f"File {rule['path']} is missing required sections: {', '.join(missing)}"
        )
    return True, ""


def validate_file_min_lines(rule: dict, project_dir: str) -> tuple[bool, str]:
    """Check that a file has at least N lines (guards against empty/stub output)."""
    path = os.path.join(project_dir, rule["path"])
    if not os.path.isfile(path):
        return False, f"Cannot validate line count — file does not exist: {rule['path']}"

    try:
        line_count = len(Path(path).read_text().splitlines())
    except Exception as e:
        return False, f"Cannot read {rule['path']}: {e}"

    min_lines = rule.get("min_lines", 1)
    if line_count < min_lines:
        return False, (
            f"File {rule['path']} has {line_count} lines, expected at least {min_lines}"
        )
    return True, ""


def validate_dir_files_contain(rule: dict, project_dir: str) -> tuple[bool, str]:
    """Check that all matching files in a directory contain required sections.

    Useful for validating dynamically-named files like topic specs (01-auth.md,
    02-api.md, etc.) that should all have the same required structure.
    """
    dir_path = os.path.join(project_dir, rule["path"])
    if not os.path.isdir(dir_path):
        return False, f"Expected output directory does not exist: {rule['path']}"

    pattern = rule.get("glob", "*.md")
    exclude = set(rule.get("exclude", []))
    required_sections = rule.get("sections", [])
    min_files = rule.get("min_files", 1)

    # Find matching files
    matched_files = []
    for filepath in sorted(glob_mod.glob(os.path.join(dir_path, pattern))):
        filename = os.path.basename(filepath)
        if filename not in exclude:
            matched_files.append(filepath)

    if len(matched_files) < min_files:
        return False, (
            f"Directory {rule['path']} has {len(matched_files)} matching files, "
            f"expected at least {min_files}"
        )

    # Check each file for required sections
    failures = []
    for filepath in matched_files:
        filename = os.path.basename(filepath)
        try:
            content = Path(filepath).read_text()
        except Exception:
            failures.append(f"{filename}: could not read file")
            continue

        missing = [s for s in required_sections if s not in content]
        if missing:
            failures.append(f"{filename}: missing {', '.join(missing)}")

    if failures:
        file_list = "; ".join(failures)
        return False, (
            f"Topic spec files in {rule['path']} are missing required sections: {file_list}"
        )
    return True, ""


VALIDATORS = {
    "file_exists": validate_file_exists,
    "file_contains": validate_file_contains,
    "file_min_lines": validate_file_min_lines,
    "dir_files_contain": validate_dir_files_contain,
}


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    # Prevent infinite loops
    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    expectations_file = os.path.join(project_dir, ".claude", "expected-output.json")

    # No expectations set — nothing to validate
    if not os.path.isfile(expectations_file):
        sys.exit(0)

    try:
        expectations = json.loads(Path(expectations_file).read_text())
    except (json.JSONDecodeError, Exception):
        # Malformed expectations file — don't block, just warn
        sys.exit(0)

    rules = expectations.get("rules", [])
    source = expectations.get("source", "unknown command")

    if not rules:
        sys.exit(0)

    # Validate each rule
    failures = []
    for rule in rules:
        rule_type = rule.get("type", "")
        validator = VALIDATORS.get(rule_type)
        if not validator:
            continue
        passed, reason = validator(rule, project_dir)
        if not passed:
            failures.append(reason)

    if failures:
        # Block — tell Claude exactly what to fix
        failure_list = "\n".join(f"  • {f}" for f in failures)
        reason = (
            f"Output validation failed for '{source}'.\n\n"
            f"The following requirements were not met:\n{failure_list}\n\n"
            f"Fix these issues before stopping. The expectations are defined in "
            f".claude/expected-output.json."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # All validations passed — clean up the expectations file
    try:
        os.remove(expectations_file)
    except OSError:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
