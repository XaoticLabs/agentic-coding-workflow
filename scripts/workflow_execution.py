#!/usr/bin/env python3
"""Small process and artifact primitives for recorded workflow commands."""

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
from datetime import datetime, timezone
from collections.abc import Callable


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def positive(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{label} must be a finite positive number")
    return float(value)


def arguments(value: object) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(arg, str) or not arg or "\0" in arg for arg in value)
    ):
        raise ValueError("command must be a nonempty array of nonempty strings")
    return value


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_dir():
        raise ValueError(f"working directory must exist inside the project: {relative}")
    return path


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_state(project: Path) -> dict:
    result = subprocess.run(
        [
            "python3",
            str(Path(__file__).resolve().parents[1] / "hooks/verification-state.py"),
            "snapshot",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def terminate(process: subprocess.Popen) -> None:
    # Kill the entire owned process group, including descendants after its leader exits.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_command(
    command: list[str],
    cwd: Path,
    log: Path,
    timeout: float,
    *,
    environment: dict | None = None,
    expected_exit: int = 0,
    cancel: Callable[[], bool] | None = None,
) -> dict:
    arguments(command)
    positive(timeout, "timeout")
    log.parent.mkdir(parents=True, exist_ok=True)
    started = timestamp()
    start = time.monotonic()
    outcome, code, error = "error", None, None
    with log.open("w") as stdout, Path(str(log) + ".stderr").open("w") as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            try:
                deadline = start + timeout
                while process.poll() is None:
                    if cancel is not None and cancel():
                        outcome = "cancelled"
                        terminate(process)
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, timeout)
                    try:
                        process.wait(timeout=min(remaining, 0.2))
                    except subprocess.TimeoutExpired:
                        continue
                code = process.returncode
                if outcome != "cancelled":
                    outcome = "passed" if code == expected_exit else "failed"
            except subprocess.TimeoutExpired:
                outcome = "timeout"
                terminate(process)
                code = process.returncode
            except BaseException:
                terminate(process)
                raise
            finally:
                terminate(process)
        except OSError as failure:
            error = str(failure)
    return {
        "command": command,
        "cwd": str(cwd),
        "started_at": started,
        "duration_seconds": time.monotonic() - start,
        "exit_code": code,
        "expected_exit": expected_exit,
        "outcome": outcome,
        "error": error,
        "stdout": str(log),
        "stderr": str(log) + ".stderr",
        "stdout_sha256": digest(log),
        "stderr_sha256": digest(Path(str(log) + ".stderr")),
    }
