#!/usr/bin/env python3
"""Cheap lifecycle observations and optional project-owned early checks."""

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from project_directory import project_directory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from failure_triage import classify, excerpt  # noqa: E402
from workflow_execution import run_command, source_state, timestamp  # noqa: E402
from workflow_notifications import notify  # noqa: E402


def project_commands(project: Path) -> tuple[dict, dict]:
    spec = importlib.util.spec_from_file_location(
        "hook_project_commands", ROOT / "scripts/project-commands.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = module.load_commands(project / ".claude/project-commands.json")
    return commands, module.project_readiness(project, commands)


def feedback(event: str, message: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": message,
                }
            }
        )
    )


def failure(project: Path, data: dict) -> None:
    directory = project / ".claude/logs"
    directory.mkdir(parents=True, exist_ok=True)
    text = excerpt(str(data.get("error", "")), 4000)
    entry = {
        "ts": timestamp(),
        "event": "PostToolUseFailure",
        "session_id": str(data.get("session_id", "")),
        "tool_name": str(data.get("tool_name", "")),
        "is_interrupt": data.get("is_interrupt") is True,
        "error": text,
        "classification": classify(text),
    }
    path = directory / "tool-failures.jsonl"
    encoded = (json.dumps(entry, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)
    # Never infer a flake from a timeout or trigger a retry from a classifier.
    if not entry["is_interrupt"]:
        feedback(
            "PostToolUseFailure",
            f"Failure observed as {entry['classification']['category']} (heuristic only). Inspect the evidence before retrying; this classification does not authorize an action.",
        )


def early_check(project: Path) -> None:
    commands, _ = project_commands(project)
    command = commands.get("quick_check")
    if not command:
        return
    directory = project / ".claude/verification"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "quick.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        before = source_state(project)
        result = run_command(
            ["bash", "-o", "pipefail", "-c", command],
            project,
            directory / "quick.stdout",
            20,
        )
        after = source_state(project)
        record = {"kind": "advisory", "checked": before, "after": after, **result}
        if before != after:
            record["outcome"] = "source_changed"
        (directory / "quick.json").write_text(json.dumps(record, indent=2) + "\n")
        if record["outcome"] != "passed":
            feedback(
                "PostToolUse",
                f"Advisory quick_check {record['outcome']}. Inspect {directory / 'quick.json'}. Final project verification is still required.",
            )


def main() -> int:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return 0
        event = sys.argv[1] if len(sys.argv) == 2 else data.get("hook_event_name")
        if event == "Stop":
            if data.get("stop_hook_active") is not True:
                notify(
                    "Claude: response finished",
                    str(
                        data.get("last_assistant_message")
                        or "Response finished; verification may still be running"
                    ),
                )
        elif event == "Notification":
            notify(
                "Claude: attention needed",
                str(data.get("message") or "Input requested"),
            )
        elif event == "PostToolUseFailure":
            failure(Path(project_directory(data)), data)
        elif event == "PostToolUse":
            early_check(Path(project_directory(data)))
        elif event == "SessionStart":
            project = Path(project_directory(data))
            _, readiness = project_commands(project)
            branch = subprocess.run(
                ["git", "-C", str(project), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            feedback(
                "SessionStart",
                f"Checkout: {project}; branch: {branch.stdout.strip() or 'detached/unknown'}; project checks: {readiness['status']}. Readiness is configuration only; checks have not run. Use the existing project commands and keep ordinary work in this session.",
            )
    except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError):
        pass  # Optional observations and notifications fail open.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
