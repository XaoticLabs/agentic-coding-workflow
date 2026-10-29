"""Relay supervisor regressions, including preservation guarantees inherited from Ralph.

The CLI model is a local fixture. These tests establish controller behavior, not
the effectiveness of a live implementation or reviewer model.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from workflow_test_support import EVALUATION, git, write_executable

ROOT = Path(__file__).resolve().parents[1]


def plan(project: Path, dependencies: dict[int, list[int]] | None = None) -> None:
    directory = project / ".claude/specs/feature"
    directory.mkdir(parents=True, exist_ok=True)
    dependencies = dependencies or {1: []}
    tasks = [
        {
            "id": number,
            "name": f"implement feature {number}",
            "status": "pending",
            "priority": "HIGH",
            "deps": deps,
            "files": [f"feature-{number}.txt"],
        }
        for number, deps in dependencies.items()
    ]
    (directory / "IMPLEMENTATION_PLAN.md").write_text(
        "## Task Index\n```json\n"
        + json.dumps({"tasks": tasks})
        + "\n```\n## Tasks\n"
        + "\n".join(
            f"### Task {number}: implement feature {number}\nCreate feature-{number}.txt containing implemented.\n"
            for number in dependencies
        )
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project = tmp_path / "project's files"
    project.mkdir()
    (project / ".gitignore").write_text(".claude/\n__pycache__/\n")
    (project / "check.py").write_text(
        "from pathlib import Path\nfor p in Path('.').glob('feature-*.txt'):\n    assert p.read_text() == 'implemented\\n', p\n"
    )
    git(project, "init", "--quiet", "-b", "main")
    git(project, "config", "user.name", "Fixture")
    git(project, "config", "user.email", "fixture@example.com")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Initial")
    plan(project)
    (project / ".claude/project-commands.json").write_text(
        json.dumps(
            {"lint": "python3 -m py_compile check.py", "test": "python3 check.py"}
        )
    )
    executable = tmp_path / "bin/claude"
    executable.parent.mkdir()
    executable.write_text(
        "#!/usr/bin/env python3\n"
        + r"""
import json, os, pathlib, subprocess, sys, time
p = pathlib.Path('.')
review = '--restricted' in sys.argv
with open(os.environ['TEST_CALLS'], 'a') as stream:
    stream.write(json.dumps({'review': review, 'argv': sys.argv[1:], 'cwd': str(p.resolve())}) + '\n')
sys.stdin.read()
if review:
    mode = os.environ.get('TEST_REVIEW_MODE', '')
    if mode == 'error': sys.exit(7)
    if mode == 'missing':
        print('{}'); sys.exit(0)
    if mode == 'hang': time.sleep(20)
    if mode == 'mutate': pathlib.Path('feature-1.txt').write_text('changed after checks')
    value = json.loads(os.environ['TEST_VALID_EVALUATION'])
    if mode == 'revise':
        value['verdict'] = 'REVISE'
        value['revise_guidance'] = 'The fixture expectation is not met'
    print(json.dumps({'is_error': False, 'subtype': 'success', 'structured_output': value, 'modelUsage': {'fixture-reviewer': {}}}))
else:
    task = os.environ['RELAY_TASK_ID']
    mode = os.environ.get('TEST_WORKER_MODE', '')
    counter = p / '.claude/attempt-count'
    counter.parent.mkdir(exist_ok=True)
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(n))
    if mode == 'hang':
        subprocess.Popen([sys.executable, '-c', "import time, pathlib; time.sleep(3); pathlib.Path(" + repr(os.environ['TEST_CHILD_MARKER']) + ").write_text('orphan')"])
        time.sleep(20)
    if mode == 'parallel':
        marker = pathlib.Path(os.environ['TEST_BARRIER'])
        (marker / task).touch()
        until = time.monotonic() + 3
        while len(list(marker.iterdir())) < 2 and time.monotonic() < until: time.sleep(.02)
        if len(list(marker.iterdir())) < 2: sys.exit(8)
    filename = 'shared.txt' if mode == 'conflict' else f'feature-{task}.txt'
    content = 'bad\n' if mode == 'bad' or (mode == 'repair' and n == 1) else 'implemented\n'
    if mode == 'conflict': content = task + '\n'
    (p / filename).write_text(content)
    if mode == 'error': sys.exit(7)
    if mode == 'missing':
        print('{}'); sys.exit(0)
    if mode == 'protected': (p / '.env').write_text('PRIVATE=fixture')
    if mode == 'disable-checks': (p / '.claude/project-commands.json').write_text('{"lint":null,"test":null}')
    if mode == 'original': (pathlib.Path(os.environ['TEST_ORIGINAL']) / 'check.py').write_text('changed')
    if mode == 'commit':
        subprocess.run(['git', 'add', '.'], check=True)
        subprocess.run(['git', 'commit', '--quiet', '-m', 'Worker commit'], check=True)
    print(json.dumps({'is_error': False, 'subtype': 'success', 'structured_output': {'status': 'ready', 'summary': 'Implemented fixture behavior'}, 'modelUsage': {'fixture-worker': {}}}))
"""
    )
    executable.chmod(0o755)
    return project


def execute(
    project: Path, *options: str, **variables: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/relay.py"), "feature", *options],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "WORKFLOW_NOTIFY": "false",
            "TEST_VALID_EVALUATION": json.dumps(EVALUATION),
            "TEST_CALLS": str(project.parent / "calls.jsonl"),
            "TEST_ORIGINAL": str(project),
            "TEST_CHILD_MARKER": str(project.parent / "orphan.txt"),
            **variables,
        },
        capture_output=True,
        text=True,
        timeout=35,
    )


def state(project: Path) -> tuple[dict, Path]:
    home = project / ".claude/relay/feature"
    run = json.loads((home / "active.json").read_text())["run"]
    directory = home / "runs" / run
    return json.loads((directory / "state.json").read_text()), directory


def calls(project: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (project.parent / "calls.jsonl").read_text().splitlines()
    ]


def test_success_accepts_checked_source_without_touching_original_or_plan(
    project: Path,
) -> None:
    before = git(project, "rev-parse", "HEAD")
    plan_file = project / ".claude/specs/feature/IMPLEMENTATION_PLAN.md"
    original_plan = plan_file.read_bytes()
    result = execute(project)
    assert result.returncode == 0, result.stdout + result.stderr
    run, directory = state(project)
    assert run["status"] == "completed"
    assert run["tasks"]["1"]["node"] == "accepted"
    assert run["checked"]["revision"] == git(Path(run["worktree"]), "rev-parse", "HEAD")
    assert (Path(run["worktree"]) / "feature-1.txt").read_text() == "implemented\n"
    assert git(project, "rev-parse", "HEAD") == before
    assert git(project, "branch", "--show-current") == "main"
    assert not (project / "feature-1.txt").exists()
    assert plan_file.read_bytes() == original_plan
    assert (directory / "completion-review/verdict.json").exists()
    worker = next(call for call in calls(project) if not call["review"])
    reviewer = next(call for call in calls(project) if call["review"])
    assert "--dangerously-skip-permissions" not in worker["argv"]
    assert reviewer["argv"][reviewer["argv"].index("--tools") + 1] == "Read,Glob,Grep"


@pytest.mark.parametrize(
    "mode, reason",
    [
        ("error", "failed"),
        ("missing", "Invalid worker"),
        ("protected", "Protected secret"),
        ("disable-checks", "frozen workflow"),
        ("commit", "Git history"),
        ("original", "Original checkout"),
    ],
)
def test_invalid_candidates_are_preserved_without_acceptance(
    project: Path, mode: str, reason: str
) -> None:
    result = execute(project, TEST_WORKER_MODE=mode)
    assert result.returncode != 0, result.stdout + result.stderr
    run, _ = state(project)
    assert run["status"] == "blocked"
    assert reason in run["reason"]
    record = run["tasks"]["1"]
    assert record["node"] != "accepted"
    assert Path(record["worktree"]).exists()
    assert git(Path(run["worktree"]), "rev-parse", "HEAD") == run["source"]["revision"]


@pytest.mark.parametrize("mode", ["revise", "error", "missing", "mutate", "hang"])
def test_reviewer_rejection_error_and_changed_source_never_accept(
    project: Path, mode: str
) -> None:
    result = execute(
        project,
        "--max-attempts=1",
        "--time-budget=1" if mode == "hang" else "--time-budget=10",
        TEST_REVIEW_MODE=mode,
    )
    assert result.returncode != 0
    run, _ = state(project)
    assert run["tasks"]["1"]["node"] != "accepted"
    assert run["head"] == run["source"]["revision"]


def test_failed_checks_repair_within_budget_and_retain_failure_evidence(
    project: Path,
) -> None:
    result = execute(project, TEST_WORKER_MODE="repair")
    assert result.returncode == 0, result.stdout + result.stderr
    run, directory = state(project)
    assert run["tasks"]["1"]["attempts"] == 2
    first = run["tasks"]["1"]["evidence"][0]["checks"]
    assert first["status"] == "failed"
    assert (directory / "task-1/attempt-1/checks/failure-observation.json").exists()


@pytest.mark.parametrize(
    "command", ["false | true", "exit 1", "printf changed >> check.py"]
)
@pytest.mark.parametrize("action", ["lint", "verify"])
def test_check_failures_and_source_mutation_block_integration(
    project: Path, command: str, action: str
) -> None:
    (project / ".claude/project-commands.json").write_text(
        json.dumps({"lint": "true", "test": "true", action: command})
    )
    result = execute(project, "--max-attempts=1")
    assert result.returncode != 0
    run, _ = state(project)
    assert run["tasks"]["1"]["evidence"][0]["checks"]["status"] == "failed"
    assert run["head"] == run["source"]["revision"]


def test_timeout_kills_owned_descendants_and_preserves_worktree(project: Path) -> None:
    result = execute(project, "--time-budget=.3", TEST_WORKER_MODE="hang")
    assert result.returncode != 0
    run, _ = state(project)
    assert "timeout" in run["reason"]
    assert Path(run["tasks"]["1"]["worktree"]).exists()
    time.sleep(3.2)
    assert not (project.parent / "orphan.txt").exists()


def test_dependencies_unlock_only_after_acceptance_and_resume_keeps_limits(
    project: Path,
) -> None:
    plan(project, {1: [], 2: [1]})
    first = execute(project, "--once")
    assert first.returncode == 2, first.stdout + first.stderr
    run, _ = state(project)
    assert run["status"] == "incomplete"
    assert run["tasks"]["1"]["node"] == "accepted"
    assert run["tasks"]["2"]["attempts"] == 0
    previous_iterations = run["iterations"]
    result = execute(project, "--resume")
    assert result.returncode == 0, result.stdout + result.stderr
    resumed, _ = state(project)
    assert resumed["id"] == run["id"]
    assert resumed["iterations"] == previous_iterations + 1
    assert resumed["consumed_seconds"] > run["consumed_seconds"]
    assert resumed["limits"] == run["limits"]


def test_failed_dependency_never_launches_a_dependent(project: Path) -> None:
    plan(project, {1: [], 2: [1]})
    result = execute(project, "--max-attempts=1", TEST_WORKER_MODE="bad")
    assert result.returncode != 0
    run, _ = state(project)
    assert run["tasks"]["2"]["attempts"] == 0


def test_independent_tasks_run_concurrently_and_integrated_source_is_rechecked(
    project: Path,
) -> None:
    plan(project, {1: [], 2: []})
    barrier = project.parent / "barrier"
    barrier.mkdir()
    result = execute(
        project, "--workers=2", TEST_WORKER_MODE="parallel", TEST_BARRIER=str(barrier)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run, directory = state(project)
    assert all(record["node"] == "accepted" for record in run["tasks"].values())
    assert len(list(Path(run["worktree"]).glob("feature-*.txt"))) == 2
    assert list(directory.glob("task-*/integration/review/verdict.json"))


def test_merge_conflict_preserves_every_candidate_and_original_branch(
    project: Path,
) -> None:
    plan(project, {1: [], 2: []})
    base = git(project, "rev-parse", "HEAD")
    result = execute(project, "--workers=2", TEST_WORKER_MODE="conflict")
    assert result.returncode != 0
    run, _ = state(project)
    assert run["status"] == "blocked"
    assert all(Path(record["worktree"]).exists() for record in run["tasks"].values())
    assert git(project, "rev-parse", "HEAD") == base
    assert "shared.txt" in git(
        Path(run["worktree"]), "diff", "--name-only", "--diff-filter=U"
    )


@pytest.mark.parametrize("change", ["source", "plan", "integration", "limits"])
def test_resume_refuses_changed_inputs_without_reset_or_new_worker(
    project: Path, change: str
) -> None:
    plan(project, {1: [], 2: [1]})
    assert execute(project, "--once").returncode == 2
    before, _ = state(project)
    count = len(calls(project))
    options = ["--resume"]
    if change == "source":
        (project / "check.py").write_text("changed")
    if change == "plan":
        (project / ".claude/specs/feature/IMPLEMENTATION_PLAN.md").write_text("changed")
    if change == "integration":
        (Path(before["worktree"]) / "feature-1.txt").write_text("changed")
    if change == "limits":
        options += ["--max=100"]
    assert execute(project, *options).returncode != 0
    assert len(calls(project)) == count
    assert Path(before["worktree"]).exists()


@pytest.mark.parametrize(
    "options",
    [
        ("--time-budget=0",),
        ("--run-budget=nan",),
        ("--max=0",),
        ("--workers=7",),
        ("--no-eval",),
        ("--harvest",),
    ],
)
def test_invalid_or_retired_controls_never_launch_workers(
    project: Path, options: tuple[str]
) -> None:
    assert execute(project, *options).returncode != 0
    assert not (project.parent / "calls.jsonl").exists()


def test_explicit_scope_policy_is_checked_before_review(project: Path) -> None:
    (project / ".claude/relay-policy.json").write_text(
        json.dumps({"allowed_paths": ["src/"], "protected_paths": []})
    )
    assert execute(project).returncode != 0
    run, _ = state(project)
    assert "outside the agreed scope" in run["reason"]
    assert not any(call["review"] for call in calls(project))


def test_once_does_not_hide_additional_repair_calls(project: Path) -> None:
    result = execute(project, "--once", TEST_WORKER_MODE="repair")
    assert result.returncode == 2, result.stdout + result.stderr
    run, _ = state(project)
    assert run["status"] == "incomplete"
    assert run["iterations"] == run["tasks"]["1"]["attempts"] == 1
    assert len([call for call in calls(project) if not call["review"]]) == 1
    resumed = execute(project, "--resume", TEST_WORKER_MODE="repair")
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr


def test_git_hooks_are_honored_and_cannot_smuggle_a_protected_change(
    project: Path,
) -> None:
    hooks = project.parent / "git-hooks"
    write_executable(hooks / "pre-commit", "printf fixture > .env\ngit add .env\n")
    git(project, "config", "core.hooksPath", str(hooks))
    result = execute(project)
    assert result.returncode != 0
    run, _ = state(project)
    assert "Protected secret" in run["reason"]
    assert not any(call["review"] for call in calls(project))


def test_ignored_native_permissions_and_project_skills_survive_worktree_creation(
    project: Path,
) -> None:
    settings = project / ".claude/settings.local.json"
    settings.write_text(json.dumps({"permissions": {"deny": ["Bash(git push*)"]}}))
    skill = project / ".claude/skills/project-policy/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: project-policy\ndescription: Project policy.\n---\nKeep the agreed behavior.\n"
    )
    result = execute(project)
    assert result.returncode == 0, result.stdout + result.stderr
    run, _ = state(project)
    assert (
        Path(run["worktree"]) / settings.relative_to(project)
    ).read_bytes() == settings.read_bytes()
    assert (
        Path(run["worktree"]) / skill.relative_to(project)
    ).read_bytes() == skill.read_bytes()


@pytest.mark.parametrize("damage", ["attempts", "workers", "active", "commands"])
def test_corrupt_checkpoints_are_rejected_before_another_worker(
    project: Path, damage: str
) -> None:
    plan(project, {1: [], 2: [1]})
    assert execute(project, "--once").returncode == 2
    run, directory = state(project)
    count = len(calls(project))
    if damage == "attempts":
        run["tasks"]["2"]["attempts"] = -1
    elif damage == "workers":
        run["limits"]["workers"] = -1
    elif damage == "commands":
        run["commands"]["test"] = "true"
    else:
        (project / ".claude/relay/feature/active.json").write_text(
            '{"run":"../../unowned"}'
        )
    (directory / "state.json").write_text(json.dumps(run))
    result = execute(project, "--resume")
    assert result.returncode != 0
    assert len(calls(project)) == count


def test_total_budget_bounds_execution_without_a_success_verdict(project: Path) -> None:
    result = execute(project, "--run-budget=1", TEST_WORKER_MODE="hang")
    assert result.returncode == 2, result.stdout + result.stderr
    run, _ = state(project)
    assert run["status"] == "stopped"
    assert run["tasks"]["1"]["node"] != "accepted"


def test_operator_stop_and_exclusive_supervisor_lock(project: Path) -> None:
    environment = {
        **os.environ,
        "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "WORKFLOW_NOTIFY": "false",
        "TEST_VALID_EVALUATION": json.dumps(EVALUATION),
        "TEST_CALLS": str(project.parent / "calls.jsonl"),
        "TEST_WORKER_MODE": "hang",
        "TEST_CHILD_MARKER": str(project.parent / "stop-orphan.txt"),
    }
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/relay.py"), "feature"],
        cwd=project,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        until = time.monotonic() + 5
        while (
            not (project.parent / "calls.jsonl").exists() and time.monotonic() < until
        ):
            time.sleep(0.02)
        duplicate = execute(project)
        assert duplicate.returncode != 0
        assert "already owns" in duplicate.stderr
        requested = execute(project, "--stop")
        assert requested.returncode == 0, requested.stderr
        output, errors = process.communicate(timeout=10)
        assert process.returncode == 2, output + errors
        run, _ = state(project)
        assert run["status"] == "stopped"
        assert Path(run["worktree"]).exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=10)
