"""Exercise the task contract through the public scheduler and validator."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def task(number: int, deps: list[int] | None = None, **fields: object) -> dict:
    return {
        "id": number,
        "name": f"Task {number}",
        "status": "pending",
        "priority": "HIGH",
        "deps": deps or [],
        "files": [f"src/{number}.py"],
        **fields,
    }


def plan(path: Path, tasks: list[dict]) -> Path:
    path.write_text(
        "## Task Index\n\n```json\n"
        + json.dumps({"tasks": tasks})
        + "\n```\n\n## Tasks\n"
    )
    return path


def schedule(path: Path, workers: str = "2") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / "scripts/partition-tasks.sh"), str(path), workers],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def test_all_dependencies_determine_waves_for_legacy_and_structured_plans(
    tmp_path: Path,
) -> None:
    tasks = [task(1), task(2, [1]), task(3, [1, 2]), task(4, [1, 2, 3])]
    structured = plan(tmp_path / "structured.md", tasks)
    legacy = tmp_path / "legacy.md"
    legacy.write_text(
        "## Task Index\n"
        + "\n".join(
            f"- [ ] **Task {item['id']}: Name** — Priority: HIGH, Deps: "
            + (", ".join(f"Task {dep}" for dep in item["deps"]) or "none")
            + f", Spec: 0{item['id']}.md, Files: src/{item['id']}.py"
            for item in tasks
        )
    )
    for path in (structured, legacy):
        result = schedule(path)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["waves"] == [
            {"wave": wave, "tasks": [wave + 1]} for wave in range(4)
        ]


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        ([task(1), task(1)], "duplicate task id"),
        ([task(1, [99])], "unknown dependency"),
        ([task(1, [1])], "self-dependency"),
        ([task(1, [2]), task(2, [3]), task(3, [1])], "dependency cycle"),
        ([task(1, [2, 2]), task(2)], "duplicate dependency"),
        ([task(1, files="src/file.py")], "files must be an array"),
        ([task(True)], "positive integer"),
        ([task(1, deps=[True])], "deps must be an array"),
    ],
)
def test_invalid_graphs_fail_before_assignment(
    tmp_path: Path, tasks: list[dict], message: str
) -> None:
    result = schedule(plan(tmp_path / "plan.md", tasks))
    assert result.returncode != 0
    assert result.stdout == ""
    assert message in result.stderr


@pytest.mark.parametrize("workers", ["0", "-1", "two"])
def test_invalid_worker_count_fails(tmp_path: Path, workers: str) -> None:
    assert schedule(plan(tmp_path / "plan.md", [task(1)]), workers).returncode != 0


def test_completed_dependencies_and_quoted_paths(tmp_path: Path) -> None:
    path = 'src/with spaces/quote"file.py'
    result = schedule(
        plan(
            tmp_path / "plan.md",
            [
                task(1, status="done"),
                task(2, [1], files=[path]),
                task(3, [2], files=[path]),
            ],
        )
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["waves"] == [{"wave": 0, "tasks": [2]}, {"wave": 1, "tasks": [3]}]
    owner = data["file_owners"][path]
    assert data["workers"][owner] == [2, 3]


def test_all_complete_is_distinct_from_missing_index(tmp_path: Path) -> None:
    path = plan(tmp_path / "plan.md", [task(1, status="done")])
    assert json.loads(schedule(path).stdout)["waves"] == []
    path.write_text("### Task 1: invisible\n- **Status:** TODO\n")
    assert schedule(path).returncode != 0


def test_legacy_plan_without_index_can_contain_json_acceptance_examples(
    tmp_path: Path,
) -> None:
    path = tmp_path / "plan.md"
    path.write_text(
        '- [ ] **Task 1: Legacy task**\n\n### Acceptance\n```json\n{"response": "ok"}\n```\n'
    )
    result = schedule(path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["waves"] == [{"wave": 0, "tasks": [1]}]


def test_partial_legacy_index_and_malformed_json_are_errors(tmp_path: Path) -> None:
    path = tmp_path / "plan.md"
    for invalid in (
        "- [ ] Task 2: bad syntax",
        "- [ ] **Task 2: Name** — Priority: HIGH, Deps: Task 1, garbage, Files: two.py",
    ):
        path.write_text("- [ ] **Task 1: Valid**\n" + invalid)
        assert schedule(path).returncode != 0
    path.write_text("## Task Index\n```json\n{broken}\n```\n")
    assert schedule(path).returncode != 0


def test_stop_validator_uses_the_same_graph_contract(tmp_path: Path) -> None:
    path = plan(tmp_path / "plan.md", [task(1, [2])])
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/expected-output.json").write_text(
        json.dumps(
            {
                "source": "test",
                "rules": [{"type": "task_index_format", "path": path.name}],
            }
        )
    )
    result = subprocess.run(
        ["python3", str(ROOT / "hooks/validate-output.py")],
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        input="{}",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "unknown dependency" in json.loads(result.stdout)["reason"]
    assert (tmp_path / ".claude/expected-output.json").exists()


def test_next_and_completion_stats_respect_worker_assignments(tmp_path: Path) -> None:
    path = plan(tmp_path / "plan.md", [task(1), task(2, [1]), task(3, status="done")])
    (tmp_path / ".claude").mkdir()
    assignment = tmp_path / ".claude/ralph-assigned-tasks"
    assignment.write_text("3")
    environment = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    stats = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/task-plan.py"),
            "stats",
            str(path),
            "--assigned",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert stats.returncode == 0, stats.stderr
    assert stats.stdout == "1 1 0\n"
    assignment.write_text("1,2")
    next_task = subprocess.run(
        ["python3", str(ROOT / "scripts/task-plan.py"), "next", str(path)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert next_task.returncode == 0, next_task.stderr
    assert next_task.stdout == "Task 1\n"


@pytest.mark.parametrize("structured", [False, True])
def test_repair_preserves_plan_details_and_resets_orphaned_completions(
    tmp_path: Path, structured: bool
) -> None:
    path = tmp_path / "plan.md"
    if structured:
        plan(path, [task(1, status="done", completed_in="f" * 40)])
    else:
        path.write_text(
            "## Task Index\n- [x] **Task 1: Name** — Priority: HIGH, Deps: none, Files: src/a.py — Completed in "
            + "f" * 40
            + "\n\n## Tasks\n"
        )
    path.write_text(
        "## Status: COMPLETE\n" + path.read_text() + "Detailed acceptance criteria\n"
    )
    repaired = subprocess.run(
        ["python3", str(ROOT / "scripts/task-plan.py"), "repair", str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert repaired.returncode == 0, repaired.stderr
    assert json.loads(repaired.stdout) == [{"id": 1, "commit": "f" * 40}]
    assert "Detailed acceptance criteria" in path.read_text()
    assert "## Status: IN_PROGRESS" in path.read_text()
    assert json.loads(schedule(path).stdout)["total_incomplete"] == 1
