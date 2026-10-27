#!/usr/bin/env python3
"""Relay: a bounded task supervisor with deterministic acceptance edges."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from enum import StrEnum
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

from failure_triage import observe
from workflow_execution import (
    positive,
    run_command,
    source_state,
    timestamp,
    write_json,
)
from workflow_models import model_arguments, observed_models, selection
from workflow_notifications import notify

ROOT = Path(__file__).resolve().parents[1]
GUIDANCE = (
    ".claude/rules",
    ".claude/specs",
    ".claude/skills",
    ".claude/project-commands.json",
    ".claude/project-environment.json",
    ".claude/AGENTS.md",
    ".claude/relay-policy.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
)
spec = importlib.util.spec_from_file_location(
    "relay_task_plan", ROOT / "scripts/task-plan.py"
)
assert spec and spec.loader
plans = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plans
spec.loader.exec_module(plans)


class Node(StrEnum):
    PENDING = "pending"
    IMPLEMENT = "implement"
    CHECK = "check"
    REVIEW = "review"
    INTEGRATE = "integrate"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


@dataclass
class TaskRecord:
    id: int
    node: str = Node.PENDING
    attempts: int = 0
    worktree: str = ""
    branch: str = ""
    base: str = ""
    commit: str = ""
    checked: dict = field(default_factory=dict)
    feedback: str = ""
    evidence: list[dict] = field(default_factory=list)


@dataclass
class Run:
    version: int
    id: str
    project: str
    spec: str
    source: dict
    plan_sha256: str
    commands: dict
    policy: dict
    limits: dict
    tasks: dict[str, TaskRecord]
    worktree: str = ""
    branch: str = ""
    head: str = ""
    checked: dict = field(default_factory=dict)
    status: str = "running"
    reason: str = ""
    iterations: int = 0
    consumed_seconds: float = 0
    started_at: str = field(default_factory=timestamp)


class Halt(RuntimeError):
    pass


class Incomplete(Halt):
    pass


def git(directory: Path, *args: str) -> str:
    output = subprocess.check_output(
        ["git", "-C", str(directory), *args],
        text=True,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    return output if "-z" in args else output.strip()


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def active_run(home: Path) -> Path:
    name = read_object(home / "active.json")["run"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise ValueError("Invalid active run identifier")
    directory = (home / "runs" / name).resolve(strict=True)
    if (
        not directory.is_relative_to((home / "runs").resolve())
        or not directory.is_dir()
    ):
        raise ValueError("Active run is outside its owned records")
    return directory


def load_run(value: dict, tasks: list) -> Run:
    value["tasks"] = {
        number: TaskRecord(**record) for number, record in value["tasks"].items()
    }
    run = Run(**value)
    if set(run.tasks) != {str(task.id) for task in tasks}:
        raise ValueError("Checkpoint tasks do not match the task graph")
    for number, record in run.tasks.items():
        if (
            type(record.id) is not int
            or str(record.id) != number
            or record.node not in set(Node)
        ):
            raise ValueError("Invalid task checkpoint identity or node")
        if type(record.attempts) is not int or record.attempts < 0:
            raise ValueError("Invalid task attempt counter")
    if set(run.limits) != {
        "workers",
        "iterations",
        "attempts",
        "node_seconds",
        "run_seconds",
    }:
        raise ValueError("Invalid checkpoint limits")
    for name, amount in run.limits.items():
        positive(amount, name)
        if name in ("workers", "iterations", "attempts") and type(amount) is not int:
            raise ValueError("Integer execution limits required")
    if (
        run.limits["workers"] > 6
        or type(run.iterations) is not int
        or run.iterations < 0
    ):
        raise ValueError("Invalid worker or iteration count")
    positive(run.consumed_seconds + 1, "recorded execution time")
    if run.consumed_seconds < 0:
        raise ValueError("Invalid recorded execution time")
    return run


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def clean(directory: Path) -> bool:
    return not git(directory, "status", "--porcelain", "--untracked-files=all")


def policy_from(project: Path) -> dict:
    path = project / ".claude/relay-policy.json"
    value = read_object(path) if path.exists() else {}
    if set(value) - {"allowed_paths", "protected_paths"}:
        raise ValueError("Relay policy accepts only allowed_paths and protected_paths")
    for name in ("allowed_paths", "protected_paths"):
        values = value.setdefault(name, [])
        if not isinstance(values, list) or any(
            not isinstance(p, str)
            or not p
            or p.startswith("/")
            or ".." in Path(p).parts
            or "\0" in p
            for p in values
        ):
            raise ValueError(f"{name} must contain project-relative paths")
    return value


def matches(path: str, patterns: list[str]) -> bool:
    return any(
        path == pattern.rstrip("/")
        or path.startswith(pattern.rstrip("/") + "/")
        or Path(path).match(pattern)
        for pattern in patterns
    )


def check_paths(paths: list[str], policy: dict) -> None:
    for name in paths:
        if any(
            part in (".env", ".aws", ".ssh", "secrets") or part.startswith(".env.")
            for part in Path(name).parts
        ):
            raise Halt(f"Protected secret path changed: {name}")
        if name.startswith(".claude/") or matches(name, policy["protected_paths"]):
            raise Halt(f"Protected workflow or project path changed: {name}")
        if policy["allowed_paths"] and not matches(name, policy["allowed_paths"]):
            raise Halt(f"Path outside the agreed scope: {name}")


def task_context(task, plan: str, directory: Path) -> str:
    details = re.search(
        rf"^### Task {task.id}\b[^\n]*\n(.*?)(?=^### Task \d+\b|^## |\Z)",
        plan,
        re.M | re.S,
    )
    topic = ""
    if task.spec:
        path = (directory / task.spec).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError(f"Task {task.id} has an invalid spec path")
        topic = path.read_text()
    context = f"Task {task.id}: {task.name}\n\n{details.group(1) if details else plan}\n\n{topic}"
    if len(context.encode()) > 120000:
        raise ValueError(
            f"Task {task.id} context is too large; split the task or its spec"
        )
    return context


class Supervisor:
    def __init__(
        self,
        run: Run,
        directory: Path,
        tasks: list,
        contexts: dict[int, str],
        triage: dict | None = None,
    ):
        self.run, self.directory = run, directory
        self.project = Path(run.project)
        self.tasks = {task.id: task for task in tasks}
        self.contexts, self.triage = contexts, triage
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.abort = threading.Event()
        self.started = time.monotonic()
        self.previous_seconds = run.consumed_seconds
        self.initial_iterations = run.iterations
        self.once = False

    def save(self) -> None:
        with self.lock:
            self.run.consumed_seconds = (
                self.previous_seconds + time.monotonic() - self.started
            )
            write_json(self.directory / "state.json", asdict(self.run))

    def event(self, node: str, **fields) -> None:
        with self.lock:
            with (self.directory / "events.jsonl").open("a") as stream:
                stream.write(
                    json.dumps({"ts": timestamp(), "node": node, **fields}) + "\n"
                )
            self.save()

    def cancelled(self) -> bool:
        return (
            self.abort.is_set()
            or self.stop.is_set()
            or (self.directory / "stop").exists()
            or self.previous_seconds + time.monotonic() - self.started
            >= self.run.limits["run_seconds"]
        )

    def budget(self) -> float:
        if self.cancelled():
            raise Halt("Operator stop or total execution budget reached")
        remaining = (
            self.run.limits["run_seconds"]
            - self.previous_seconds
            - (time.monotonic() - self.started)
        )
        return min(self.run.limits["node_seconds"], remaining)

    def process(
        self,
        command: list[str],
        cwd: Path,
        log: Path,
        *,
        environment: dict | None = None,
    ) -> dict:
        result = run_command(
            command,
            cwd,
            log,
            self.budget(),
            environment=environment,
            cancel=self.cancelled,
        )
        write_json(Path(str(log) + ".result.json"), result)
        self.event(
            "process",
            command=command[:3],
            outcome=result["outcome"],
            record=str(log) + ".result.json",
        )
        return result

    def stable_project(self) -> None:
        if source_state(self.project) != self.run.source:
            raise Halt(
                "Original checkout, guidance, or plan changed; preserve work and reassess"
            )

    def mutate_git(self, path: Path, log: Path, *args: str) -> None:
        result = self.process(["git", "-C", str(path), *args], path, log)
        if result["outcome"] != "passed":
            raise Halt(f"Git {args[0]} {result['outcome']}; inspect {result['stderr']}")

    def worktree(self, label: str, base: str) -> tuple[Path, str]:
        branch = f"relay/{self.run.id}/{label}"
        path = self.project / ".claude/worktrees" / f"relay-{self.run.id}-{label}"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.mutate_git(
            self.project,
            self.directory / "setup" / f"{label}.stdout",
            "worktree",
            "add",
            "-b",
            branch,
            str(path),
            base,
        )
        # Share the existing ownership contract with explicit worktree cleanup.
        subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; register_worktree_owner "$2" "$3" "$4"; release_worktree "$2" "$3"',
                "relay",
                str(ROOT / "scripts/lib/worktree-safety.sh"),
                str(self.project),
                str(path),
                base,
            ],
            env={**os.environ, "WORKTREE_OWNER_TOKEN": self.run.id},
            check=True,
            capture_output=True,
            timeout=30,
        )
        # Copy only ignored workflow guidance. Tracked guidance is in the commit.
        for relative in GUIDANCE:
            original = self.project / relative
            if not original.exists() or original.is_symlink():
                continue
            files = list(original.rglob("*")) if original.is_dir() else [original]
            for source in files:
                if source.is_symlink():
                    raise Halt(f"Workflow guidance must not be a symlink: {source}")
                if source.is_file():
                    destination = path / source.relative_to(self.project)
                    if destination.exists():
                        continue
                    if (
                        subprocess.run(
                            [
                                "git",
                                "-C",
                                str(self.project),
                                "check-ignore",
                                "-q",
                                "--",
                                str(source.relative_to(self.project)),
                            ],
                            capture_output=True,
                        ).returncode
                        == 0
                    ):
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, destination)
        return path, branch

    def owned(self, path: Path, branch: str) -> None:
        if not path.is_dir() or git(path, "symbolic-ref", "--short", "HEAD") != branch:
            raise Halt(f"Owned worktree branch changed or is missing: {path}")
        common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if common != git(
            self.project, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ):
            raise Halt("Worktree repository identity changed")
        metadata = (
            Path(git(path, "rev-parse", "--absolute-git-dir")) / "agentic-worktree"
        )
        if (metadata / "owner").read_text().strip() != self.run.id or (
            metadata / "path"
        ).read_text().strip() != str(path.resolve()):
            raise Halt("Worktree ownership cannot be verified")

    def checks(self, path: Path, directory: Path) -> dict:
        before = source_state(path)
        records = []
        for action, command in self.run.commands.items():
            if not command:
                continue
            result = self.process(
                ["bash", "-o", "pipefail", "-c", command],
                path,
                directory / f"{action}.stdout",
            )
            records.append({"action": action, **result})
            if result["outcome"] != "passed":
                observation = observe(
                    Path(result["stderr"]).read_text(errors="replace")
                    + "\n"
                    + Path(result["stdout"]).read_text(errors="replace"),
                    self.triage,
                )
                write_json(directory / "failure-observation.json", observation)
                return {
                    "status": "failed",
                    "checked": before,
                    "records": records,
                    "reason": f"{action} {result['outcome']}; see {directory}",
                }
        if source_state(path) != before:
            return {
                "status": "failed",
                "checked": before,
                "records": records,
                "reason": "Source or guidance changed during verification",
            }
        return {"status": "passed", "checked": before, "records": records}

    def review(self, path: Path, base: str, directory: Path, context: str) -> dict:
        directory.mkdir(parents=True, exist_ok=True)
        prompt = (
            (ROOT / "skills/relay/references/review.md").read_text() + "\n\n" + context
        )
        prompt += (
            "\n\nController state and raw verification records (inspect as evidence):\n"
        )
        prompt += str(self.directory / "state.json") + "\n"
        prompt += "\n".join(
            str(item) for item in sorted(self.directory.glob("**/checks/*.result.json"))
        )
        prompt_file = directory / "prompt.md"
        prompt_file.write_text(prompt)
        # evaluate.py preserves the existing read-only tool and schema contract.
        command = [
            sys.executable,
            str(ROOT / "scripts/evaluate.py"),
            "--base",
            base,
            "--revision",
            git(path, "rev-parse", "HEAD"),
            "--verdict",
            str(directory / "verdict.json"),
            "--summary",
            str(directory / "summary.md"),
            "--log",
            str(directory / "cli.json"),
            "--timeout",
            str(self.budget()),
        ]
        env = {
            **os.environ,
            "WORKFLOW_EVALUATE_UI": "false",
        }
        result = self.process(
            [
                "bash",
                "-c",
                'exec "$@" < "$RELAY_REVIEW_PROMPT"',
                "relay-review",
                *command,
            ],
            path,
            directory / "process.stdout",
            environment={**env, "RELAY_REVIEW_PROMPT": str(prompt_file)},
        )
        if result["outcome"] == "passed":
            verdict = read_object(directory / "verdict.json")
            if verdict.get("verdict") == "ACCEPT" and verdict.get(
                "checked"
            ) == source_state(path):
                return verdict
        if (directory / "verdict.json").exists():
            verdict = read_object(directory / "verdict.json")
            if verdict.get("verdict") == "REVISE":
                return verdict
        raise Halt(f"Independent review unavailable or stale: {directory}")

    def transition(self, record: TaskRecord, node: Node, **fields) -> None:
        with self.lock:
            record.node = node
            self.event(node, task=record.id, attempt=record.attempts, **fields)

    def validate_candidate(self, path: Path, base: str) -> list[str]:
        committed = git(
            path, "diff", "--name-only", "--no-renames", "-z", base, "HEAD"
        ).split("\0")
        changed = git(path, "diff", "--name-only", "--no-renames", "-z", "HEAD").split(
            "\0"
        )
        changed += git(path, "ls-files", "--others", "--exclude-standard", "-z").split(
            "\0"
        )
        changed = [name for name in changed if name]
        check_paths([name for name in committed + changed if name], self.run.policy)
        # Ignored guidance is part of source fingerprints but not git diff.
        for relative in GUIDANCE:
            original, candidate = self.project / relative, path / relative
            if not original.exists() and candidate.exists():
                raise Halt(f"Worker added frozen workflow guidance: {relative}")
            if original.is_file() and (
                not candidate.is_file()
                or original.read_bytes() != candidate.read_bytes()
            ):
                raise Halt(f"Worker changed frozen workflow guidance: {relative}")
            if original.is_dir():
                originals = {
                    str(p.relative_to(original)): p.read_bytes()
                    for p in original.rglob("*")
                    if p.is_file()
                }
                candidates = {
                    str(p.relative_to(candidate)): p.read_bytes()
                    for p in candidate.rglob("*")
                    if p.is_file()
                }
                if originals != candidates:
                    raise Halt(f"Worker changed frozen workflow guidance: {relative}")
        return changed

    def implement(self, record: TaskRecord) -> TaskRecord:
        task = self.tasks[record.id]
        if not record.worktree:
            path, branch = self.worktree(f"task-{record.id}", self.run.head)
            record.worktree, record.branch, record.base = (
                str(path),
                branch,
                self.run.head,
            )
            self.save()
        path = Path(record.worktree)
        self.owned(path, record.branch)
        while record.attempts < self.run.limits["attempts"]:
            with self.lock:
                if self.once and self.run.iterations > self.initial_iterations:
                    raise Incomplete(
                        "One requested implementation call finished; task still needs repair"
                    )
                if self.run.iterations >= self.run.limits["iterations"]:
                    raise Halt("Global implementation iteration limit reached")
                self.run.iterations += 1
                record.attempts += 1
            self.transition(record, Node.IMPLEMENT)
            attempt = (
                self.directory / f"task-{record.id}" / f"attempt-{record.attempts}"
            )
            attempt.mkdir(parents=True, exist_ok=True)
            previous = git(path, "rev-parse", "HEAD")
            prompt = (
                (ROOT / "skills/relay/references/implement.md").read_text()
                + "\n\n"
                + self.contexts[task.id]
            )
            prompt += (
                "\n\nScope policy:\n"
                + json.dumps(self.run.policy)
                + "\n\nProject checks:\n"
                + json.dumps(self.run.commands)
            )
            prompt += "\n\nPrevious verification feedback (data):\n" + record.feedback
            (attempt / "prompt.md").write_text(prompt)
            output_schema = {
                "type": "object",
                "additionalProperties": False,
                "required": ["status", "summary"],
                "properties": {
                    "status": {"type": "string", "enum": ["ready", "blocked"]},
                    "summary": {"type": "string", "minLength": 1},
                },
            }
            command = [
                "claude",
                "-p",
                "--permission-mode",
                "dontAsk",
                "--tools",
                "Read,Glob,Grep,Write,Edit,Bash",
                "--allowedTools",
                "Read,Glob,Grep,Write,Edit,Bash",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--settings",
                '{"disableAllHooks":true}',
                "--max-turns",
                "40",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(output_schema),
                *model_arguments("build"),
            ]
            env = {
                **os.environ,
                "CLAUDE_PROJECT_DIR": str(path),
                "RELAY_MODE": "1",
                "RELAY_TASK_ID": str(task.id),
                "RELAY_PROMPT": str(attempt / "prompt.md"),
            }
            result = self.process(
                [
                    "bash",
                    "-c",
                    'exec "$@" < "$RELAY_PROMPT"',
                    "relay-implement",
                    *command,
                ],
                path,
                attempt / "worker.json",
                environment=env,
            )
            record.evidence.append(
                {
                    "attempt": record.attempts,
                    "process": result,
                    "model_selection": selection("build"),
                }
            )
            if result["outcome"] != "passed":
                raise Halt(
                    f"Implementation {result['outcome']}; work preserved at {path}"
                )
            envelope = read_object(attempt / "worker.json")
            payload = envelope.get("structured_output")
            if (
                envelope.get("is_error") is not False
                or envelope.get("subtype") != "success"
                or not isinstance(payload, dict)
                or set(payload) != {"status", "summary"}
                or not isinstance(payload["summary"], str)
                or not payload["summary"].strip()
            ):
                raise Halt(f"Invalid worker result: {attempt / 'worker.json'}")
            record.evidence[-1]["observed_models"] = observed_models(envelope)
            if payload["status"] != "ready":
                raise Halt(f"Worker blocked: {payload['summary']}")
            self.owned(path, record.branch)
            self.stable_project()
            if git(path, "rev-parse", "HEAD") != previous:
                raise Halt("Worker changed Git history; controller owns commits")
            changed = self.validate_candidate(path, record.base)
            if changed:
                self.mutate_git(path, attempt / "git-add.stdout", "add", "--all")
                self.mutate_git(
                    path,
                    attempt / "git-commit.stdout",
                    "commit",
                    "-m",
                    f"feat: {task.name}",
                )
            record.commit = git(path, "rev-parse", "HEAD")
            self.validate_candidate(path, record.base)
            self.transition(record, Node.CHECK, commit=record.commit)
            checked = self.checks(path, attempt / "checks")
            record.evidence[-1]["checks"] = checked
            if checked["status"] != "passed":
                record.feedback = (
                    checked["reason"]
                    + "\n"
                    + "\n".join(
                        Path(item["stderr"]).read_text(errors="replace")[-4000:]
                        + Path(item["stdout"]).read_text(errors="replace")[-4000:]
                        for item in checked["records"]
                    )
                )
                if source_state(path) != checked["checked"]:
                    raise Halt(record.feedback)
                continue
            self.transition(record, Node.REVIEW)
            verdict = self.review(
                path, record.base, attempt / "review", self.contexts[task.id]
            )
            record.evidence[-1]["review"] = str(attempt / "review/verdict.json")
            if verdict["verdict"] != "ACCEPT":
                record.feedback = verdict["revise_guidance"]
                continue
            if (
                source_state(path) != checked["checked"]
                or verdict["checked"] != checked["checked"]
            ):
                raise Halt("Candidate changed after checks or review")
            record.checked = checked["checked"]
            self.transition(record, Node.INTEGRATE)
            return record
        raise Halt(f"Task {record.id} exhausted its {record.attempts} attempts")

    def integrate(self, record: TaskRecord) -> None:
        path = Path(self.run.worktree)
        self.owned(path, self.run.branch)
        self.owned(Path(record.worktree), record.branch)
        self.stable_project()
        if git(path, "rev-parse", "HEAD") != self.run.head or not clean(path):
            raise Halt("Integration source changed outside the supervisor")
        if source_state(Path(record.worktree)) != record.checked:
            raise Halt("Worker candidate changed after acceptance checks")
        if self.run.head == record.base:
            self.mutate_git(
                path,
                self.directory / f"task-{record.id}" / "integration/git.stdout",
                "merge",
                "--ff-only",
                record.commit,
            )
        elif record.commit != record.base:
            commits = git(
                Path(record.worktree),
                "rev-list",
                "--reverse",
                f"{record.base}..{record.commit}",
            ).splitlines()
            self.mutate_git(
                path,
                self.directory / f"task-{record.id}" / "integration/git.stdout",
                "cherry-pick",
                *commits,
            )
        checked = source_state(path)
        # A fast-forward can reuse evidence only for exactly the checked inputs.
        if checked != record.checked:
            evidence = self.directory / f"task-{record.id}" / "integration"
            gate = self.checks(path, evidence / "checks")
            if gate["status"] != "passed":
                raise Halt(
                    "Integrated candidate failed checks; preserve integration worktree"
                )
            context = "\n\n".join(
                self.contexts[item.id]
                for item in self.run.tasks.values()
                if item.node == Node.ACCEPTED or item.id == record.id
            )
            verdict = self.review(
                path, self.run.source["revision"], evidence / "review", context
            )
            if verdict["verdict"] != "ACCEPT" or verdict["checked"] != gate["checked"]:
                raise Halt("Integrated candidate lacks current independent acceptance")
            checked = gate["checked"]
        if source_state(path) != checked:
            raise Halt("Integrated source changed after verification")
        self.budget()
        self.stable_project()
        self.owned(path, self.run.branch)
        self.run.head, self.run.checked = git(path, "rev-parse", "HEAD"), checked
        self.transition(record, Node.ACCEPTED, integrated=self.run.head)

    def execute(self, once: bool = False) -> int:
        self.once = once
        try:
            self.stable_project()
            if not self.run.worktree:
                path, branch = self.worktree("integration", self.run.head)
                self.run.worktree, self.run.branch = str(path), branch
                self.save()
            else:
                self.owned(Path(self.run.worktree), self.run.branch)
                if git(
                    Path(self.run.worktree), "rev-parse", "HEAD"
                ) != self.run.head or not clean(Path(self.run.worktree)):
                    raise Halt(
                        "Recovery needs inspection: integration worktree differs from its checkpoint"
                    )
                if self.run.checked:
                    gate = self.checks(
                        Path(self.run.worktree), self.directory / "recovery/checks"
                    )
                    verdict = self.review(
                        Path(self.run.worktree),
                        self.run.source["revision"],
                        self.directory / "recovery/review",
                        "\n\n".join(self.contexts.values()),
                    )
                    if (
                        gate["status"] != "passed"
                        or verdict["verdict"] != "ACCEPT"
                        or gate["checked"] != verdict["checked"]
                    ):
                        raise Halt(
                            "Recovery checks did not establish current acceptance"
                        )
                    self.run.checked = gate["checked"]
                for record in self.run.tasks.values():
                    if record.node != Node.ACCEPTED:
                        if record.worktree and record.base != self.run.head:
                            raise Halt(
                                "Recovery preserves a worker on an older base; inspect it before starting a new run"
                            )
                        record.node = Node.PENDING
            while any(
                record.node != Node.ACCEPTED for record in self.run.tasks.values()
            ):
                self.budget()
                if once and self.run.iterations > self.initial_iterations:
                    self.run.status, self.run.reason = (
                        "incomplete",
                        "One requested iteration completed; resume to continue",
                    )
                    return 2
                ready = [
                    self.tasks[record.id]
                    for record in self.run.tasks.values()
                    if record.node != Node.ACCEPTED
                    and all(
                        self.run.tasks[str(dep)].node == Node.ACCEPTED
                        for dep in self.tasks[record.id].deps
                    )
                ]
                ready.sort(
                    key=lambda task: (
                        {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[task.priority],
                        task.id,
                    )
                )
                available = min(
                    1 if once else self.run.limits["workers"],
                    self.run.limits["iterations"] - self.run.iterations,
                )
                selected = []
                for task in ready:
                    if len(selected) >= available:
                        break
                    # Unknown or overlapping file ownership stays serial.
                    if selected and (
                        not task.files
                        or any(
                            not item.files
                            or any(
                                matches(p, item.files) or matches(q, task.files)
                                for p in task.files
                                for q in item.files
                            )
                            for item in selected
                        )
                    ):
                        continue
                    selected.append(task)
                if not selected:
                    raise Halt("No eligible task within the remaining iteration budget")
                failures = []
                with ThreadPoolExecutor(max_workers=len(selected)) as pool:
                    futures = {
                        pool.submit(
                            self.implement, self.run.tasks[str(task.id)]
                        ): task.id
                        for task in selected
                    }
                    for future in as_completed(futures):
                        try:
                            record = future.result()
                            if not failures:
                                self.integrate(record)
                        except Incomplete:
                            raise
                        except (
                            OSError,
                            ValueError,
                            KeyError,
                            subprocess.SubprocessError,
                            Halt,
                        ) as failure:
                            failures.append(str(failure))
                            self.run.tasks[str(futures[future])].node = Node.BLOCKED
                            self.abort.set()
                if failures:
                    raise Halt("; ".join(failures))
            self.stable_project()
            path = Path(self.run.worktree)
            if not self.run.checked:
                gate = self.checks(path, self.directory / "final/checks")
                verdict = self.review(
                    path,
                    self.run.source["revision"],
                    self.directory / "final/review",
                    "\n\n".join(self.contexts.values()),
                )
                if (
                    gate["status"] != "passed"
                    or verdict["verdict"] != "ACCEPT"
                    or gate["checked"] != verdict["checked"]
                ):
                    raise Halt("Final acceptance could not be established")
                self.run.checked = gate["checked"]
            if source_state(path) != self.run.checked:
                raise Halt("Final candidate changed after verification")
            verdict = self.review(
                path,
                self.run.source["revision"],
                self.directory / "completion-review",
                "\n\n".join(self.contexts.values()),
            )
            if verdict["verdict"] != "ACCEPT" or verdict["checked"] != self.run.checked:
                raise Halt("Final graph acceptance is missing or stale")
            self.budget()
            self.stable_project()
            self.owned(path, self.run.branch)
            self.run.status, self.run.reason = (
                "completed",
                "All tasks accepted on the preserved integration branch; publishing is separate",
            )
            return 0
        except Incomplete as failure:
            self.run.status, self.run.reason = "incomplete", str(failure)
            return 2
        except (
            OSError,
            ValueError,
            KeyError,
            subprocess.SubprocessError,
            Halt,
        ) as failure:
            self.run.status = (
                "stopped"
                if self.stop.is_set()
                or (self.directory / "stop").exists()
                or self.previous_seconds + time.monotonic() - self.started
                >= self.run.limits["run_seconds"]
                else "blocked"
            )
            self.run.reason = str(failure)
            return 2 if self.run.status == "stopped" else 1
        finally:
            self.save()
            self.event("finish", status=self.run.status, reason=self.run.reason)
            notify(f"Relay: {self.run.status}", self.run.reason)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "spec", help="Spec slug under .claude/specs, or a spec directory"
    )
    result.add_argument(
        "--project", type=Path, default=Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    )
    action = result.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true")
    action.add_argument("--stop", action="store_true")
    action.add_argument("--resume", action="store_true")
    result.add_argument("--once", action="store_true")
    result.add_argument("--workers", "--parallel", type=int)
    result.add_argument("--max", dest="iterations", type=int)
    result.add_argument("--max-attempts", dest="attempts", type=int)
    result.add_argument("--time-budget", dest="node_seconds", type=float)
    result.add_argument("--run-budget", dest="run_seconds", type=float)
    result.add_argument(
        "--triage-config",
        type=Path,
        help="Explicit opt-in for observation-only decision API calls",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        project = args.project.resolve(strict=True)
        if Path(git(project, "rev-parse", "--show-toplevel")) != project:
            raise ValueError("Relay must run at the Git checkout root")
        requested = Path(args.spec)
        directory = requested if requested.is_absolute() else project / requested
        if not directory.is_dir() and "/" not in args.spec:
            directory = project / ".claude/specs" / args.spec
        directory = directory.resolve()
        if not directory.is_relative_to(project) or not directory.is_dir():
            raise ValueError("Spec directory must exist inside the project")
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", directory.name)
        home = project / ".claude/relay" / slug
        active = home / "active.json"
        if args.status or args.stop:
            run_dir = active_run(home)
            if args.stop:
                (run_dir / "stop").touch()
            print((run_dir / "state.json").read_text())
            return 0
        home.mkdir(parents=True, exist_ok=True)
        with (home / "supervisor.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("A Relay supervisor already owns this spec") from None
            plan_path = directory / "IMPLEMENTATION_PLAN.md"
            text = plan_path.read_text()
            tasks = plans.load_plan(plan_path)
            if not tasks:
                raise ValueError("Relay requires at least one task")
            contexts = {task.id: task_context(task, text, directory) for task in tasks}
            defaults = {
                "workers": 1,
                "iterations": 50,
                "attempts": 3,
                "node_seconds": 600,
                "run_seconds": 3600,
            }
            if args.resume:
                run_dir = active_run(home)
                value = read_object(run_dir / "state.json")
                run = load_run(value, tasks)
                if (
                    run.version != 1
                    or run.id != run_dir.name
                    or run.project != str(project)
                    or run.spec != str(directory)
                    or run.plan_sha256 != hash_text(text)
                    or run.status == "completed"
                ):
                    raise ValueError(
                        "Run cannot resume: completed, incompatible, or changed plan/project"
                    )
                if policy_from(project) != run.policy:
                    raise ValueError("Relay policy changed; reassess in a new run")
                configured = read_object(project / ".claude/project-commands.json")
                current_commands = {
                    key: configured[key]
                    for key in ("lint", "test", "verify")
                    if key in configured
                }
                if current_commands != run.commands:
                    raise ValueError(
                        "Checkpoint check commands differ from project-owned configuration"
                    )
                for key in defaults:
                    if (
                        getattr(args, key) is not None
                        and getattr(args, key) != run.limits[key]
                    ):
                        raise ValueError(
                            "Resume retains original limits; start a new run for different limits"
                        )
                (run_dir / "stop").unlink(missing_ok=True)
                run.status, run.reason = "running", ""
            else:
                if not clean(project):
                    raise ValueError(
                        "Commit or isolate current source changes before starting Relay"
                    )
                commands_file = project / ".claude/project-commands.json"
                command_spec = importlib.util.spec_from_file_location(
                    "relay_commands", ROOT / "scripts/project-commands.py"
                )
                assert command_spec and command_spec.loader
                command_module = importlib.util.module_from_spec(command_spec)
                command_spec.loader.exec_module(command_module)
                configured = command_module.load_commands(commands_file)
                if any(action not in configured for action in ("lint", "test")):
                    raise ValueError(
                        "Configure project lint and test commands (or explicit null disables) before Relay"
                    )
                commands = {
                    key: configured[key]
                    for key in ("lint", "test", "verify")
                    if key in configured
                }
                if not any(commands.values()):
                    raise ValueError(
                        "Relay requires at least one executable verification command"
                    )
                limits = {
                    key: getattr(args, key)
                    if getattr(args, key) is not None
                    else default
                    for key, default in defaults.items()
                }
                for key, value in limits.items():
                    positive(value, key)
                if limits["workers"] > 6:
                    raise ValueError("Relay supports one to six workers")
                run_id = (
                    f"{slug}-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
                )
                run_dir = home / "runs" / run_id
                run_dir.mkdir(parents=True)
                source = source_state(project)
                run = Run(
                    1,
                    run_id,
                    str(project),
                    str(directory),
                    source,
                    hash_text(text),
                    commands,
                    policy_from(project),
                    limits,
                    {
                        str(task.id): TaskRecord(
                            task.id,
                            node=Node.ACCEPTED
                            if task.status == "done"
                            else Node.PENDING,
                        )
                        for task in tasks
                    },
                    head=source["revision"],
                )
                write_json(active, {"run": run_id})
            triage = read_object(args.triage_config) if args.triage_config else None
            supervisor = Supervisor(run, run_dir, tasks, contexts, triage)
            previous = {
                sig: signal.signal(sig, lambda *_: supervisor.stop.set())
                for sig in (signal.SIGINT, signal.SIGTERM)
            }
            try:
                code = supervisor.execute(args.once)
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
            print(
                json.dumps(
                    {
                        "status": run.status,
                        "reason": run.reason,
                        "branch": run.branch,
                        "worktree": run.worktree,
                        "state": str(run_dir / "state.json"),
                    },
                    indent=2,
                )
            )
            return code
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ) as failure:
        print(f"Relay: {failure}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
