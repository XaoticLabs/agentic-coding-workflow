#!/usr/bin/env python3
"""Run project commands and services in a private, disposable Linux container."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from workflow_execution import (
    arguments,
    contained,
    digest,
    positive,
    run_command,
    source_state,
    terminate,
    timestamp,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ".claude/project-environment.json"


def recipe(path: Path) -> dict:
    value = json.loads(path.read_text())
    allowed = {
        "version",
        "engine",
        "image",
        "network",
        "cpus",
        "memory",
        "pids_limit",
        "timeout_seconds",
        "pass_env",
        "services",
    }
    if not isinstance(value, dict) or set(value) - allowed or value.get("version") != 1:
        raise ValueError(
            "environment recipe must be a version 1 object with supported fields"
        )
    image = value.get("image", "")
    if not isinstance(image, str) or not re.fullmatch(
        r"(?:[^\s]+@)?sha256:[a-f0-9]{64}", image
    ):
        raise ValueError(
            "image must be a pinned repository@sha256 digest or local sha256 image ID"
        )
    if value.get("engine", "podman") not in ("podman", "docker"):
        raise ValueError("engine must be podman or docker")
    if value.get("network", "none") not in ("none", "bridge"):
        raise ValueError(
            "network must be none or bridge; host networking is unsupported"
        )
    positive(value.get("cpus", 2), "cpus")
    positive(value.get("timeout_seconds", 600), "timeout_seconds")
    if not isinstance(value.get("memory", "2g"), str) or not re.fullmatch(
        r"[1-9][0-9]*[mg]", value.get("memory", "2g")
    ):
        raise ValueError("memory must be a positive integer with m or g suffix")
    pids = value.get("pids_limit", 256)
    if isinstance(pids, bool) or not isinstance(pids, int) or pids < 16:
        raise ValueError("pids_limit must be an integer of at least 16")
    environment = value.get("pass_env", [])
    if not isinstance(environment, list) or any(
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
        or name in {"HOME", "PATH", "LD_PRELOAD", "PYTHONPATH"}
        for name in environment
    ):
        raise ValueError(
            "pass_env must list explicit environment names, excluding runtime overrides"
        )
    services = value.get("services", [])
    if not isinstance(services, list):
        raise ValueError("services must be an array")
    names = set()
    for service in services:
        if not isinstance(service, dict) or set(service) - {
            "name",
            "command",
            "ready",
            "cwd",
            "timeout_seconds",
        }:
            raise ValueError("invalid service fields")
        name = service.get("name", "")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z][a-z0-9-]*", name)
            or name in names
        ):
            raise ValueError("service names must be unique lowercase identifiers")
        names.add(name)
        arguments(service.get("command"))
        arguments(service.get("ready"))
        positive(service.get("timeout_seconds", 30), "service timeout")
        if not isinstance(service.get("cwd", "."), str):
            raise ValueError("service cwd must be a project-relative directory")
    return value


def sensitive(path: Path) -> bool:
    return any(
        part in {".git", ".aws", ".ssh", "secrets"}
        or (part.startswith(".env") and part not in {".env.example", ".env.sample"})
        for part in path.parts
    )


def stage_source(project: Path, workspace: Path, includes: list[str]) -> None:
    files = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=project,
    ).split(b"\0")
    names = {os.fsdecode(name) for name in files if name}
    names = {name for name in names if Path(name).parts[0] != ".claude"}
    names.update(includes)
    for name in sorted(names):
        relative = Path(name)
        source = project / relative
        if source.is_relative_to(workspace.parent):
            continue
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or sensitive(relative)
            or not source.resolve().is_relative_to(project)
        ):
            raise ValueError(f"source path cannot be exported: {name}")
        if source.is_symlink():
            raise ValueError(
                f"source symlinks require an explicit project export strategy: {name}"
            )
        if not source.exists():
            if name in includes:
                raise ValueError(f"included file does not exist: {name}")
            continue  # A locally deleted tracked file stays deleted in the snapshot.
        if not source.is_file():
            raise ValueError(f"only regular source files can be exported: {name}")
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def container_command(config: dict, run: Path, name: str) -> list[str]:
    engine = config.get("engine", "podman")
    command = [
        engine,
        "run",
        "--name",
        name,
        "--pull",
        "never",
        "--rm",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--network",
        config.get("network", "none"),
        "--cpus",
        str(config.get("cpus", 2)),
        "--memory",
        config.get("memory", "2g"),
        "--pids-limit",
        str(config.get("pids_limit", 256)),
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--env",
        "XDG_CACHE_HOME=/tmp/cache",
        "--env",
        f"WORKFLOW_RUN_ID={name}",
        "--workdir",
        "/workspace",
    ]
    if engine == "podman":
        command += ["--userns", "keep-id"]
    for source, destination, mode in (
        (run / "workspace", "/workspace", "rw"),
        (run / "tooling", "/workflow", "ro"),
        (run / "artifacts", "/artifacts", "rw"),
    ):
        # Podman's :Z relabels only the private run directories, never the checkout.
        command += ["--volume", f"{source}:{destination}:{mode},Z"]
    for name in config.get("pass_env", []):
        if name not in os.environ:
            raise ValueError(f"required environment variable is unavailable: {name}")
        command += ["--env", name]  # Values never appear in argv or reports.
    return [
        *command,
        "--entrypoint",
        "python3",
        config["image"],
        "/workflow/project-environment.py",
        "--inside",
    ]


def inside() -> int:
    job = json.loads(Path("/workflow/job.json").read_text())
    project, output = Path("/workspace"), Path("/artifacts")
    services, handles, checks = [], [], []
    report = {
        "status": "ERROR",
        "checks": checks,
        "services": [],
        "started_at": timestamp(),
    }
    try:
        # A local baseline enables a candidate patch without touching host Git metadata.
        for command in (
            ["git", "init", "--quiet"],
            ["git", "add", "."],
            [
                "git",
                "-c",
                "user.name=Workflow",
                "-c",
                "user.email=workflow@localhost",
                "commit",
                "--quiet",
                "--allow-empty",
                "-m",
                "Input snapshot",
            ],
        ):
            subprocess.run(command, cwd=project, check=True, capture_output=True)
        for step in job["steps"]:
            if step["action"] == "install":
                check = run_command(
                    step["command"],
                    project,
                    output / "install.log",
                    job["recipe"].get("timeout_seconds", 600),
                )
                checks.append({"action": "install", **check})
                if check["outcome"] != "passed":
                    raise ValueError(f"install {check['outcome']}")
        for service in job["recipe"].get("services", []):
            cwd = contained(project, service.get("cwd", "."))
            log = output / f"service-{service['name']}.log"
            stdout, stderr = log.open("w"), Path(str(log) + ".stderr").open("w")
            handles.extend((stdout, stderr))
            process = subprocess.Popen(
                service["command"],
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            services.append(process)
            deadline, attempt = time.monotonic() + service.get("timeout_seconds", 30), 0
            while True:
                attempt += 1
                remaining = deadline - time.monotonic()
                if process.poll() is not None or remaining <= 0:
                    raise ValueError(f"service failed readiness: {service['name']}")
                probe = run_command(
                    service["ready"],
                    cwd,
                    output / f"ready-{service['name']}-{attempt}.log",
                    min(remaining, 5),
                )
                if probe["outcome"] == "passed":
                    report["services"].append(
                        {"name": service["name"], "readiness": probe}
                    )
                    break
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        for index, step in enumerate(job["steps"]):
            if step["action"] == "install":
                continue
            check = run_command(
                step["command"],
                project,
                output / f"check-{index}.log",
                job["recipe"].get("timeout_seconds", 600),
            )
            checks.append({"action": step["action"], **check})
            if check["outcome"] != "passed":
                raise ValueError(f"{step['action']} {check['outcome']}")
            if any(process.poll() is not None for process in services):
                raise ValueError("a required service exited during verification")
        report["status"] = "PASSED"
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["reason"] = str(error)
    finally:
        for process in reversed(services):
            terminate(process)
        for handle in handles:
            handle.close()
        # Patch generation also stays inside the container.
        try:
            subprocess.run(
                ["git", "add", "--intent-to-add", "."],
                cwd=project,
                check=True,
                capture_output=True,
            )
            with (output / "candidate.patch").open("wb") as patch:
                subprocess.run(
                    ["git", "--no-pager", "diff", "--no-ext-diff", "--binary", "HEAD"],
                    cwd=project,
                    stdout=patch,
                    check=True,
                )
        except (OSError, subprocess.SubprocessError):
            report["patch"] = "unavailable; candidate workspace retained"
        report["finished_at"] = timestamp()
        write_json(output / "result.json", report)
    return 0 if report["status"] == "PASSED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--actions", nargs="+", default=[])
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="optional command after --, executed after selected actions",
    )
    args = parser.parse_args()
    if args.inside:
        return inside()
    record, run = None, None
    try:
        project = args.project_dir.resolve()
        config = recipe(project / CONFIG)
        if "install" in args.actions and args.actions[0] != "install":
            raise ValueError("install must be the first selected action")
        steps = []
        for action in args.actions:
            selected = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/project-commands.py"),
                    "get",
                    str(project),
                    action,
                ],
                text=True,
                capture_output=True,
            )
            if selected.returncode or not selected.stdout.strip():
                raise ValueError(
                    f"required action {action} is missing, disabled, or invalid: {selected.stderr.strip()}"
                )
            steps.append(
                {
                    "action": action,
                    "command": ["bash", "-o", "pipefail", "-c", selected.stdout],
                }
            )
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if command:
            steps.append({"action": "command", "command": arguments(command)})
        if not steps:
            raise ValueError("select --actions or supply a command after --")
        before = source_state(project)
        name = "workflow-" + uuid.uuid4().hex
        run = (args.output_dir or project / ".claude/environments" / name).resolve()
        run.mkdir(parents=True, exist_ok=False)
        for directory in ("workspace", "tooling", "artifacts"):
            (run / directory).mkdir()
        for filename in ("project-environment.py", "workflow_execution.py"):
            shutil.copy2(ROOT / "scripts" / filename, run / "tooling" / filename)
        write_json(run / "tooling/job.json", {"recipe": config, "steps": steps})
        stage_source(project, run / "workspace", args.include)
        invocation = container_command(config, run, name)
        record = {
            "status": "NOT_RUN",
            "candidate": before,
            "recipe_sha256": digest(project / CONFIG),
            "tooling_sha256": {
                filename: digest(run / "tooling" / filename)
                for filename in (
                    "project-environment.py",
                    "workflow_execution.py",
                    "job.json",
                )
            },
            "command": invocation,
            "steps": steps,
            "workspace": str(run / "workspace"),
            "started_at": timestamp(),
        }
        write_json(run / "run.json", record)
        if not args.dry_run:
            if not shutil.which(config.get("engine", "podman")):
                raise ValueError(
                    "configured container engine is unavailable; no host fallback"
                )
            try:
                execution = run_command(
                    invocation,
                    project,
                    run / "container.log",
                    config.get("timeout_seconds", 600),
                )
                record["execution"] = execution
            finally:
                # Unique name belongs to this invocation. Cleanup never targets other containers.
                cleanup = subprocess.run(
                    [config.get("engine", "podman"), "rm", "--force", name],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                record["cleanup_exit"] = cleanup.returncode
            result_path = run / "artifacts/result.json"
            record["status"] = "ERROR"
            if result_path.is_symlink():
                raise ValueError(
                    "container result must be a regular file, not a symlink"
                )
            if result_path.is_file():
                result = json.loads(result_path.read_text())
                if not isinstance(result, dict):
                    raise ValueError("container result must be a JSON object")
                record["result"] = result
                if (
                    execution["outcome"] == "passed"
                    and result.get("status") == "PASSED"
                ):
                    record["status"] = "PASSED"
            if execution["outcome"] == "timeout":
                record["status"] = "TIMEOUT"
            if source_state(project) != before:
                record["status"] = "INVALID_SOURCE_CHANGED"
            write_json(run / "run.json", record)
        print(
            json.dumps(
                {
                    "status": record["status"],
                    "record": str(run / "run.json"),
                    "workspace": str(run / "workspace"),
                }
            )
        )
        return 0 if args.dry_run or record["status"] == "PASSED" else 2
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if record is not None and run is not None:
            record.update(status="ERROR", reason=str(error))
            write_json(run / "run.json", record)
        print(f"Environment error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
