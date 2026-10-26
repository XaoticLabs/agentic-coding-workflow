#!/usr/bin/env python3
"""Run the native plugin evaluator with explicit models, split, limits and provenance."""

import argparse
import json
from pathlib import Path
import shutil
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
    parser.add_argument("--split", choices=("tuning", "holdout"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    parser.add_argument("--runs", type=int, default=3, choices=range(1, 51))
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--case", default="*")
    parser.add_argument(
        "--frozen-revision", help="required clean HEAD for final holdout"
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--not-run-reason", help="reason retained with --dry-run")
    parser.add_argument(
        "--shell", action="store_true", help="grant Bash for reviewed runtime cases"
    )
    args = parser.parse_args()
    record, output = None, None
    try:
        positive(args.max_cost_usd, "max-cost-usd")
        positive(args.timeout, "timeout")
        if args.not_run_reason and not args.dry_run:
            raise ValueError("--not-run-reason requires --dry-run")
        before = source_state(ROOT)
        if args.split == "holdout":
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
            dirty = subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()
            if not args.frozen_revision or args.frozen_revision != head or dirty:
                raise ValueError(
                    "holdout requires a clean checkout and --frozen-revision equal to HEAD"
                )
        output = (
            args.output_dir
            or ROOT
            / "evals/results"
            / f"{timestamp().replace(':', '-')}-{uuid.uuid4().hex[:8]}"
        ).resolve()
        output.mkdir(parents=True, exist_ok=False)
        command = [
            "claude",
            "plugin",
            "eval",
            str(ROOT),
            "--tag",
            args.split,
            "--case",
            args.case,
            "--model",
            args.model,
            "--judge-model",
            args.judge_model,
            "--runs",
            str(args.runs),
            "--ablation",
            "with-without",
            "--concurrency",
            "1",
            "--max-cost-usd",
            str(args.max_cost_usd),
            "--allow-tools",
            "Write",
            "Edit",
            *(["Bash"] if args.shell else []),
            "--scaffold",
            "--trust-plugin",
            "--no-publish",
            "--output-dir",
            str(output / "native"),
            "--json",
            str(output / "native.json"),
        ]
        record = {
            "status": "NOT_RUN",
            "command": command,
            "candidate": before,
            "split": args.split,
            "requested_models": {"execution": args.model, "judge": args.judge_model},
            "runs_per_arm_requested": args.runs,
            "started_at": timestamp(),
            "reason": args.not_run_reason or "dry run",
        }
        write_json(output / "run.json", record)
        if not args.dry_run:
            if not shutil.which("claude"):
                record["reason"] = "Claude Code CLI is not installed"
            else:
                version = subprocess.run(
                    ["claude", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True,
                )
                record["cli_version"] = version.stdout.strip()
                authentication = subprocess.run(
                    ["claude", "auth", "status"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if (
                    authentication.returncode
                    or json.loads(authentication.stdout).get("loggedIn") is not True
                ):
                    record["reason"] = (
                        "Claude Code is not authenticated; no model calls made"
                    )
                    write_json(output / "run.json", record)
                    print(
                        json.dumps(
                            {
                                "status": "NOT_RUN",
                                "reason": record["reason"],
                                "record": str(output / "run.json"),
                            }
                        )
                    )
                    return 2
                execution = run_command(
                    command, ROOT, output / "runner.log", args.timeout
                )
                record.update(
                    execution=execution,
                    status="ERROR",
                    reason="native results unavailable or incomplete",
                )
                native_path = output / "native.json"
                if native_path.is_file():
                    native = json.loads(native_path.read_text())
                    if (
                        not isinstance(native, dict)
                        or not isinstance(native.get("cases"), list)
                        or not native["cases"]
                    ):
                        raise ValueError(
                            "native evaluator returned no valid case results"
                        )
                    record["native_report"] = str(native_path)
                    if native.get("partial"):
                        record.update(
                            status="INCOMPLETE",
                            reason="native evaluator reported partial results",
                        )
                    elif execution["outcome"] in ("passed", "failed") and execution[
                        "exit_code"
                    ] in (0, 1):
                        record.update(
                            status="PASSED"
                            if execution["exit_code"] == 0
                            else "FAILED",
                            reason="see native per-case outcomes and observed models",
                        )
                if source_state(ROOT) != before:
                    record.update(
                        status="INVALID",
                        reason="candidate or verification inputs changed during evaluation",
                    )
        write_json(output / "run.json", record)
        print(
            json.dumps(
                {
                    "status": record["status"],
                    "reason": record["reason"],
                    "record": str(output / "run.json"),
                }
            )
        )
        return 0 if args.dry_run or record["status"] == "PASSED" else 2
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if record is not None and output is not None:
            record.update(status="ERROR", reason=str(error))
            write_json(output / "run.json", record)
        print(f"Evaluation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
