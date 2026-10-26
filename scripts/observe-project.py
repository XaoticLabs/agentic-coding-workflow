#!/usr/bin/env python3
"""Record project-configured health, logs, deployment or flag observations."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from workflow_execution import (
    positive,
    run_command,
    source_state,
    timestamp,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--actions",
        nargs="+",
        choices=("health", "logs", "deploy_status", "flag_status"),
        required=True,
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        positive(args.timeout, "timeout")
        if not args.target.strip() or "\0" in args.target:
            raise ValueError("target must be nonempty")
        project = args.project_dir.resolve()
        commands = []
        for action in args.actions:
            selected = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/project-commands.py"),
                    "get",
                    str(project),
                    action,
                ],
                capture_output=True,
                text=True,
            )
            if selected.returncode or not selected.stdout.strip():
                raise ValueError(
                    f"{action} is missing, disabled, or invalid; configure the project's read-only observation command"
                )
            commands.append((action, selected.stdout))
        before = source_state(project)
        output = (
            args.output_dir or project / ".claude/observations" / uuid.uuid4().hex
        ).resolve()
        output.mkdir(parents=True, exist_ok=False)
        checks = []
        record = {
            "status": "RUNNING",
            "target": args.target,
            "candidate": before,
            "started_at": timestamp(),
            "observations": checks,
        }
        write_json(output / "observations.json", record)
        for action, command in commands:
            checks.append(
                {
                    "action": action,
                    **run_command(
                        ["bash", "-o", "pipefail", "-c", command],
                        project,
                        output / f"{action}.log",
                        args.timeout,
                        environment={**os.environ, "WORKFLOW_TARGET": args.target},
                    ),
                }
            )
            write_json(output / "observations.json", record)
        record["status"] = (
            "OBSERVED"
            if all(check["outcome"] == "passed" for check in checks)
            else "NEEDS_ATTENTION"
        )
        if source_state(project) != before:
            record["status"] = "INVALID_SOURCE_CHANGED"
        record["finished_at"] = timestamp()
        write_json(output / "observations.json", record)
        print(
            json.dumps(
                {
                    "status": record["status"],
                    "record": str(output / "observations.json"),
                }
            )
        )
        return 0 if record["status"] == "OBSERVED" else 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Observation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
