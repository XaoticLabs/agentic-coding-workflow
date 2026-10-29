#!/usr/bin/env python3
"""Exercise public verification entrypoints and retain reproducible local evidence."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workflow_execution import run_command, source_state, write_json  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def exercise(project: Path, evidence: Path, criteria: list[str]) -> None:
    sequence = 0

    def run(label: str, command: list[str], *, expected_exit: int = 0) -> str:
        nonlocal sequence
        sequence += 1
        log = evidence / f"{sequence:02d}-{label}.stdout"
        result = run_command(
            command,
            project,
            log,
            30,
            expected_exit=expected_exit,
            environment={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        )
        write_json(log.with_suffix(".result.json"), result)
        require(result["outcome"] == "passed", f"{label}: inspect {log}")
        return log.read_text()

    (project / ".claude").mkdir()
    (project / ".gitignore").write_text(".claude/\n")
    behavior = project / "behavior.txt"
    behavior.write_text("broken\n")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Delivery smoke",
            "-c",
            "user.email=smoke@localhost",
            "commit",
            "--quiet",
            "-m",
            "baseline",
        ],
    ):
        run("setup", command)
    verify = "printf 'exercise\\n' >> .claude/check-runs; grep -qx working behavior.txt"
    write_json(
        project / ".claude/project-commands.json",
        {"lint": "true", "test": "true", "verify": verify},
    )
    commands = [sys.executable, str(ROOT / "scripts/project-commands.py")]
    readiness = json.loads(run("readiness", [*commands, "readiness", str(project)]))
    require(readiness["status"] == "configured", "Project should be configured")
    require(
        readiness["verification"] == "not_run", "Readiness must not claim execution"
    )
    selected = run("get-verify", [*commands, "get", str(project), "verify"])
    require(selected == verify, "Command reader must preserve the product command")
    criteria.append(
        "Public command reader reports the configured product check without executing it"
    )

    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["Stop"]
    stop = next(
        hook["command"]
        for group in hooks
        for hook in group["hooks"]
        if "hooks/lint-on-stop.sh" in hook.get("command", "")
    )
    stop_argv = shlex.split(stop.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)))

    def stop_check(label: str, *, active: bool, status: str) -> dict:
        payload = json.dumps(
            {"session_id": "delivery-smoke", "stop_hook_active": active}
        )
        output = run(
            label,
            [
                "bash",
                "-o",
                "pipefail",
                "-c",
                'printf \'%s\' "$1" | "${@:2}"',
                "smoke",
                payload,
                *stop_argv,
            ],
        )
        record = json.loads(
            next((project / ".claude/verification").glob("*.json")).read_text()
        )
        write_json(evidence / f"{label}.record.json", record)
        require(record["status"] == status, f"{label}: unexpected verification status")
        require(record["checked"] == record["after"], f"{label}: check mutated source")
        if status == "passed":
            require(output == "", f"{label}: successful Stop should allow completion")
        else:
            response = json.loads(output)
            require(
                response.get("decision") == "block", f"{label}: failure must block Stop"
            )
            require(
                "project verify" in response["reason"],
                f"{label}: product failure must be reported",
            )
        return record

    gate_command = [
        "bash",
        "-c",
        'set -euo pipefail\nsource "$1"\nrun_verification_gate "$2" "$3"',
        "smoke",
        str(ROOT / "scripts/lib/parallel-primitives.sh"),
        str(project),
    ]
    run(
        "shared-failure",
        [*gate_command, str(evidence / "failed-gate")],
        expected_exit=1,
    )
    failed = stop_check("stop-failure", active=False, status="failed")
    criteria.append(
        "Product failure blocks the shared delivery gate and the registered Stop command"
    )

    behavior.write_text("working\n")
    run("shared-success", [*gate_command, str(evidence / "passed-gate")])
    passed = stop_check("stop-corrected", active=True, status="passed")
    require(
        passed["checked"] != failed["checked"],
        "Correction must check the changed source",
    )
    criteria.append("Corrected behavior passes both routes on the current source")

    calls = project / ".claude/check-runs"
    before_reuse = calls.read_text()
    stop_check("stop-reused", active=True, status="passed")
    require(
        calls.read_text() == before_reuse,
        "Unchanged correction turn should reuse success",
    )
    criteria.append("Cached success is reused only for unchanged source")

    behavior.write_text("regressed\n")
    changed = stop_check("stop-regressed", active=True, status="failed")
    require(
        changed["checked"] != passed["checked"], "Source edit must invalidate success"
    )
    require(
        calls.read_text() != before_reuse, "Source edit must rerun the product check"
    )
    (evidence / "check-runs.txt").write_text(calls.read_text())
    criteria.append(
        "A subsequent source change invalidates success and blocks regression"
    )


def main() -> int:
    parent = ROOT / ".claude/proofs/delivery"
    parent.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    summary: dict = {
        "status": "failed",
        "scope": "Local hook/CLI exercise in a disposable Git project; no model or provider fixtures",
        "native_session": "NOT_RUN: exercise in Claude Code separately",
        "criteria": [],
    }
    scratch = None
    try:
        summary["checked"] = source_state(ROOT)
        with tempfile.TemporaryDirectory(prefix="workflow delivery's ") as directory:
            scratch = Path(directory)
            exercise(scratch, evidence, summary["criteria"])
        summary["after"] = source_state(ROOT)
        require(
            summary["checked"] == summary["after"],
            "Plugin source changed during verification",
        )
        summary["status"] = "passed"
    except (
        OSError,
        ValueError,
        RuntimeError,
        StopIteration,
        subprocess.SubprocessError,
    ) as error:
        summary["error"] = str(error)
    finally:
        summary["cleanup"] = (
            "passed" if scratch is not None and not scratch.exists() else "unavailable"
        )
        if summary["cleanup"] != "passed":
            summary["status"] = "failed"
        write_json(evidence / "summary.json", summary)
    print(f"Delivery verification {summary['status']}: {evidence / 'summary.json'}")
    if "error" in summary:
        print(summary["error"], file=sys.stderr)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
