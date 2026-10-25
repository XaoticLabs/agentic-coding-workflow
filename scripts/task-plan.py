#!/usr/bin/env python3
"""Load structured task indexes, validate their DAG, and schedule pending tasks.

The canonical index is a JSON object {"tasks": [...]} in a fenced JSON block
under ## Task Index. Legacy checkbox indexes are accepted at this boundary.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Task:
    id: int
    name: str
    status: str
    priority: str
    deps: list[int]
    files: list[str]
    spec: str = ""
    completed_in: str = ""


def task_from_json(value: object) -> Task:
    if not isinstance(value, dict):
        raise ValueError("each task must be an object")
    required = {"id", "name", "status", "priority", "deps", "files"}
    if required - value.keys():
        raise ValueError(f"task is missing fields: {sorted(required - value.keys())}")
    if value.keys() - required - {"spec", "completed_in"}:
        raise ValueError(
            f"unknown task fields: {sorted(value.keys() - required - {'spec', 'completed_in'})}"
        )
    if type(value["id"]) is not int or value["id"] <= 0:
        raise ValueError("task id must be a positive integer")
    if not isinstance(value["name"], str) or not value["name"].strip():
        raise ValueError("task name must be a nonempty string")
    if value["status"] not in ("pending", "done"):
        raise ValueError("task status must be pending or done")
    if value["priority"] not in ("HIGH", "MEDIUM", "LOW"):
        raise ValueError("task priority must be HIGH, MEDIUM, or LOW")
    if not isinstance(value["deps"], list) or any(
        type(dep) is not int or dep <= 0 for dep in value["deps"]
    ):
        raise ValueError("task deps must be an array of positive integer ids")
    if not isinstance(value["files"], list) or any(
        not isinstance(file, str) or not file or "\0" in file for file in value["files"]
    ):
        raise ValueError("task files must be an array of nonempty paths")
    for field in ("spec", "completed_in"):
        if field in value and not isinstance(value[field], str):
            raise ValueError(f"task {field} must be a string")
    return Task(**value)


def legacy_tasks(content: str) -> list[Task]:
    tasks = []
    pattern = re.compile(r"^- \[([ xX])\] \*\*Task (\d+): (.+?)\*\*(.*)$")
    for line in content.splitlines():
        match = pattern.fullmatch(line)
        if not match:
            if re.match(r"^- \[.*?\].*\bTask\b", line):
                raise ValueError(f"malformed task index line: {line}")
            continue
        status, number, name, metadata = match.groups()
        fields = dict(
            re.findall(
                r"(?:^|, | — )(Priority|Deps|Spec|Files|Completed in):? (.*?)(?=, (?:Priority|Deps|Spec|Files):| — Completed in |$)",
                metadata,
            )
        )
        if metadata and ("Priority" not in fields or "Deps" not in fields):
            raise ValueError(
                f"Task {number}: malformed legacy metadata; use a JSON index"
            )
        deps_text = fields.get("Deps", "none")
        if deps_text.lower() == "none":
            deps = []
        elif re.fullmatch(r"Task \d+(?:,\s*Task \d+)*", deps_text):
            deps = [int(dep) for dep in re.findall(r"\d+", deps_text)]
        else:
            raise ValueError(f"Task {number}: malformed dependencies: {deps_text}")
        tasks.append(
            task_from_json(
                {
                    "id": int(number),
                    "name": name,
                    "status": "done" if status.lower() == "x" else "pending",
                    "priority": fields.get("Priority", "MEDIUM"),
                    "deps": deps,
                    "files": fields.get("Files", "").split(),
                    "spec": fields.get("Spec", ""),
                    "completed_in": fields.get("Completed in", ""),
                }
            )
        )
    if not tasks:
        raise ValueError("no task index found; add a structured JSON ## Task Index")
    return tasks


def dependency_order(tasks: list[Task]) -> list[Task]:
    by_id = {}
    for task in tasks:
        if task.id in by_id:
            raise ValueError(f"duplicate task id: {task.id}")
        by_id[task.id] = task
    for task in tasks:
        if len(set(task.deps)) != len(task.deps):
            raise ValueError(f"Task {task.id}: duplicate dependency")
        for dep in task.deps:
            if dep not in by_id:
                raise ValueError(f"Task {task.id}: unknown dependency {dep}")
            if dep == task.id:
                raise ValueError(f"Task {task.id}: self-dependency")
    remaining = {task.id: set(task.deps) for task in tasks}
    ordered = []
    while remaining:
        ready = [number for number, deps in remaining.items() if not deps]
        if not ready:
            raise ValueError(f"dependency cycle involving tasks {sorted(remaining)}")
        for number in ready:
            ordered.append(by_id[number])
            del remaining[number]
        for deps in remaining.values():
            deps.difference_update(ready)
    return ordered


def load_plan(path: Path) -> list[Task]:
    content = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        decoded = json.loads(content)
    else:
        section = re.search(
            r"^## Task Index\s*\n(.*?)(?=^## |\Z)", content, re.M | re.S
        )
        index = section.group(1) if section else content
        blocks = (
            re.findall(r"^```json\s*\n(.*?)^```\s*$", index, re.M | re.S)
            if section
            else []
        )
        if len(blocks) > 1:
            raise ValueError("Task Index must have exactly one JSON block")
        if not blocks:
            if section and "```" in index:
                raise ValueError("malformed JSON Task Index fence")
            tasks = legacy_tasks(index)
            dependency_order(tasks)
            return tasks
        if re.search(r"^- \[", index, re.M):
            raise ValueError("Task Index mixes JSON and legacy checkboxes")
        decoded = json.loads(blocks[0])
    if (
        not isinstance(decoded, dict)
        or set(decoded) != {"tasks"}
        or not isinstance(decoded["tasks"], list)
    ):
        raise ValueError('Task Index must be an object containing a "tasks" array')
    tasks = [task_from_json(value) for value in decoded["tasks"]]
    dependency_order(tasks)
    return tasks


def partition(tasks: list[Task], workers: int, plan: Path) -> dict:
    if workers <= 0:
        raise ValueError("num-workers must be a positive integer")
    task_waves = {}
    for task in dependency_order(tasks):
        task_waves[task.id] = (
            -1
            if task.status == "done"
            else max((task_waves[dep] for dep in task.deps), default=-1) + 1
        )
    pending = [task for task in tasks if task.status == "pending"]
    owners = {}
    assignments = {f"worker-{worker}": [] for worker in range(workers)}
    learnings = (
        Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
        / ".claude/ralph"
        / plan.parent.name
        / "learnings.json"
    )
    hotspots = set()
    if learnings.exists():
        data = json.loads(learnings.read_text())
        hotspots = {
            file
            for file, info in data.get("conflict_hotspots", {}).items()
            if info.get("conflicts", 0) >= 2
        }
    waves = []
    for wave in range(max(task_waves.values(), default=-1) + 1):
        wave_tasks = [task for task in pending if task_waves[task.id] == wave]
        waves.append({"wave": wave, "tasks": [task.id for task in wave_tasks]})
        for task in wave_tasks:
            overlap = Counter()
            for file in task.files:
                if file in owners:
                    overlap[owners[file]] += 2 if file in hotspots else 1
            worker = min(
                assignments,
                key=lambda worker: (-overlap[worker], len(assignments[worker])),
            )
            assignments[worker].append(task.id)
            for file in task.files:
                owners.setdefault(file, worker)
    return {
        "workers": assignments if pending else {},
        "waves": waves,
        "file_owners": owners,
        "total_incomplete": len(pending),
        "num_workers": workers,
    }


def render_task(task: Task) -> str:
    deps = ", ".join(f"Task {dep}" for dep in task.deps) or "none"
    return f"- [{'x' if task.status == 'done' else ' '}] **Task {task.id}: {task.name}** — Priority: {task.priority}, Deps: {deps}, Spec: {task.spec}, Files: {' '.join(task.files)}"


def repair_plan(path: Path, tasks: list[Task]) -> list[dict]:
    content = path.read_text()
    repairs = []
    for task in tasks:
        if task.status != "done" or not task.completed_in:
            continue
        reachable = subprocess.run(
            ["git", "merge-base", "--is-ancestor", task.completed_in, "HEAD"],
            capture_output=True,
        )
        if reachable.returncode == 0:
            continue
        repairs.append({"id": task.id, "commit": task.completed_in})
        task.status, task.completed_in = "pending", ""
        content = re.sub(
            rf"^(- )\[[xX]\](.*\*\*Task {task.id}:.*?) — Completed in .*?$",
            r"\1[ ]\2",
            content,
            flags=re.M,
        )
        print(
            f"INTEGRITY: Task {task.id} references an unreachable commit; re-marking pending",
            file=sys.stderr,
        )
    if repairs:
        content = content.replace("## Status: COMPLETE", "## Status: IN_PROGRESS")
        section = re.search(
            r"^## Task Index\s*\n(.*?)(?=^## |\Z)", content, re.M | re.S
        )
        if section and "```json" in section.group(1):
            index = (
                "\n```json\n"
                + json.dumps({"tasks": [asdict(task) for task in tasks]}, indent=2)
                + "\n```\n\n"
            )
            content = content[: section.start(1)] + index + content[section.end(1) :]
        if path.suffix == ".json":
            content = (
                json.dumps({"tasks": [asdict(task) for task in tasks]}, indent=2) + "\n"
            )
        path.write_text(content)
    return repairs


def assigned_ids(tasks: list[Task]) -> set[int] | None:
    path = (
        Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude/ralph-assigned-tasks"
    )
    if not path.exists():
        return None
    assigned = {int(number) for number in path.read_text().strip().split(",")}
    if assigned - {task.id for task in tasks}:
        raise ValueError("assignment references unknown task ids")
    return assigned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=(
            "validate",
            "partition",
            "stats",
            "next",
            "remaining",
            "render",
            "repair",
        ),
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument("workers", nargs="?", type=int)
    parser.add_argument("--field", choices=("name", "spec"), default="name")
    parser.add_argument(
        "--assigned",
        action="store_true",
        help="scope stats to this worker's assignment",
    )
    args = parser.parse_args()
    try:
        tasks = load_plan(args.plan)
        pending = [task for task in tasks if task.status == "pending"]
        if args.operation == "partition":
            if args.workers is None:
                raise ValueError("num-workers is required")
            print(json.dumps(partition(tasks, args.workers, args.plan)))
        elif args.operation == "stats":
            assigned = assigned_ids(tasks) if args.assigned else None
            scoped = [task for task in tasks if assigned is None or task.id in assigned]
            remaining = sum(task.status == "pending" for task in scoped)
            print(len(scoped), len(scoped) - remaining, remaining)
        elif args.operation == "next":
            done = {task.id for task in tasks if task.status == "done"}
            assigned = assigned_ids(tasks)
            ready = [
                task
                for task in pending
                if set(task.deps) <= done and (assigned is None or task.id in assigned)
            ]
            if ready:
                print(getattr(ready[0], args.field))
        elif args.operation in ("remaining", "render"):
            for task in pending if args.operation == "remaining" else tasks:
                print(render_task(task))
        elif args.operation == "repair":
            print(json.dumps(repair_plan(args.plan, tasks)))
        else:
            print(json.dumps({"tasks": [asdict(task) for task in tasks]}))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Error: {args.plan}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
