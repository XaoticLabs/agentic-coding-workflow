#!/usr/bin/env python3

"""Validate registered task graphs on Stop using the scheduler's parser.

Ralph plan generation and write-spec --ralph register task_index_format rules
in .claude/expected-output.json. Document headings and other artifact rules
are ignored, including expectations left by older plugin versions.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

from project_directory import project_directory


def validate_task_index_format(rule: dict, project_dir: str) -> tuple[bool, str]:
    """Use the scheduler's parser and graph validation at plan creation time."""
    path = os.path.join(project_dir, rule["path"])
    if not os.path.isfile(path):
        return (
            False,
            f"Cannot validate task index — file does not exist: {rule['path']}",
        )

    try:
        module_path = Path(__file__).resolve().parents[1] / "scripts/task-plan.py"
        spec = importlib.util.spec_from_file_location("workflow_task_plan", module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        tasks = module.load_plan(Path(path))
        if len(tasks) < rule.get("min_tasks", 1):
            return False, f"File {rule['path']} has too few tasks"
    except (OSError, ValueError) as error:
        return False, f"Invalid task graph in {rule['path']}: {error}"
    return True, ""


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    if not isinstance(input_data, dict):
        sys.exit(0)

    # Prevent infinite loops
    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    try:
        project_dir = project_directory(input_data)
    except (OSError, ValueError, TypeError):
        print(json.dumps({
            "decision": "block",
            "reason": "The active checkout is unavailable; the task graph has not been verified.",
        }))
        return
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
        if rule.get("type") != "task_index_format":
            continue
        passed, reason = validate_task_index_format(rule, project_dir)
        if not passed:
            failures.append(reason)

    if failures:
        # Block — tell Claude exactly what to fix
        failure_list = "\n".join(f"  • {f}" for f in failures)
        reason = (
            f"Task graph validation failed for '{source}'.\n\n"
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
