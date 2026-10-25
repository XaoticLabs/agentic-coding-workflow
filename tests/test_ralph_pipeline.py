"""Check Ralph's process statuses through the loop's recorded outcomes."""

import csv
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LOOP = Path("skills/ralph/scripts/loop.sh")


def write_executable(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + contents)
    path.chmod(0o755)


def git(project: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(project), *arguments],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def plugin(tmp_path: Path) -> Path:
    plugin_dir = tmp_path / "plugin with spaces"
    for relative in (
        LOOP,
        Path("skills/ralph/references/PROMPT_build.md"),
        Path("scripts/lib/parallel-primitives.sh"),
        Path("scripts/project-commands.py"),
    ):
        destination = plugin_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PLUGIN_ROOT / relative, destination)
    write_executable(
        plugin_dir / "skills/ralph/scripts/stream-processor.py",
        'cat\nexit "$TEST_PROCESSOR_EXIT"\n',
    )
    write_executable(
        tmp_path / "bin/claude",
        'cat > "$CLAUDE_PROJECT_DIR/prompt.txt"\n'
        'if [ "$TEST_COMMIT" = true ]; then\n'
        '  printf "change\\n" > changed.txt\n'
        "  git add changed.txt\n"
        '  git commit --quiet -m "Implement task"\n'
        "fi\n"
        'printf "Claude output\\n"\n'
        'if [ "$TEST_HANG" = true ]; then sleep 30; fi\n'
        'exit "$TEST_CLAUDE_EXIT"\n',
    )
    return plugin_dir


@pytest.fixture
def project(plugin: Path) -> Path:
    project_dir = plugin.parent / "project with spaces"
    spec = project_dir / ".claude/specs/status-test"
    spec.mkdir(parents=True)
    (spec / "IMPLEMENTATION_PLAN.md").write_text(
        "## Status: IN_PROGRESS\n- [ ] **Task 1: Pipeline status**\n"
    )
    (project_dir / ".gitignore").write_text(".claude/\nprompt.txt\n")
    git(project_dir, "init", "--quiet")
    git(project_dir, "config", "user.name", "Test")
    git(project_dir, "config", "user.email", "test@example.com")
    git(project_dir, "add", ".gitignore")
    git(project_dir, "commit", "--quiet", "-m", "Initial commit")
    return project_dir


def run_loop(
    project: Path,
    *,
    time_budget: str = "0",
    claude_exit: int = 0,
    processor_exit: int = 0,
    hang: bool = False,
    commit: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(project.parent / "plugin with spaces" / LOOP),
            str(project / ".claude/specs/status-test"),
            "build",
            "1",
            "--once",
            f"--time-budget={time_budget}",
        ],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "CLAUDE_PROJECT_DIR": str(project),
            "RALPH_WORKER_ID": "test-worker",
            "RALPH_NOTIFY": "false",
            "TEST_CLAUDE_EXIT": str(claude_exit),
            "TEST_PROCESSOR_EXIT": str(processor_exit),
            "TEST_HANG": str(hang).lower(),
            "TEST_COMMIT": str(commit).lower(),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def assert_outcome(
    project: Path,
    outcome: str,
    verdict: str,
    *,
    journal_outcome: str | None = None,
) -> None:
    artifacts = project / ".claude/ralph/status-test"
    run = next((artifacts / "runs").iterdir())
    events = [
        json.loads(line) for line in (run / "trace.jsonl").read_text().splitlines()
    ]
    iteration = next(event for event in events if event["type"] == "iteration_end")
    assert iteration["outcome"] == outcome
    verdict_event = next(event for event in events if event["type"] == "verdict")
    assert verdict_event["outcome"] == verdict
    with (artifacts / "journal.tsv").open() as journal:
        entry = next(csv.DictReader(journal, delimiter="\t"))
    assert entry["outcome"] == (journal_outcome or verdict)
    if verdict == "NO_COMMIT":
        assert entry["notes"] == outcome
    assert f" | {outcome} | Pipeline status" in (run / "orchestrator.log").read_text()
    dashboard = (project / ".claude/ralph/status.md").read_text()
    assert f"**Last result:** {outcome}" in dashboard


@pytest.mark.parametrize("time_budget", ["0", "5"])
@pytest.mark.parametrize("claude_exit", [0, 7])
def test_claude_status_reaches_recorded_outcomes(
    project: Path, time_budget: str, claude_exit: int
) -> None:
    result = run_loop(project, time_budget=time_budget, claude_exit=claude_exit)

    assert result.returncode == 0, result.stderr
    outcome = "success" if claude_exit == 0 else f"error (code {claude_exit})"
    assert_outcome(project, outcome, "NO_COMMIT")
    assert "Stream processor exited" not in result.stderr
    if claude_exit != 0:
        assert "exited with error (code 7)" in result.stdout
        assert "completed successfully" not in result.stdout


def test_timeout_reaches_recorded_outcomes(project: Path) -> None:
    if shutil.which("timeout") is None and shutil.which("gtimeout") is None:
        pytest.skip("GNU timeout is required")

    result = run_loop(project, time_budget="1", hang=True)

    assert result.returncode == 0, result.stderr
    assert "timed out after 1s" in result.stdout
    assert "completed successfully" not in result.stdout
    assert "Stream processor exited" not in result.stderr
    assert_outcome(project, "timeout", "TIMEOUT")


@pytest.mark.parametrize("claude_exit", [0, 7])
def test_processor_failure_warns_without_replacing_claude_status(
    project: Path, claude_exit: int
) -> None:
    result = run_loop(project, claude_exit=claude_exit, processor_exit=9)

    assert result.returncode == 0, result.stderr
    assert "Stream processor exited with code 9" in result.stderr
    outcome = "success" if claude_exit == 0 else f"error (code {claude_exit})"
    assert_outcome(project, outcome, "NO_COMMIT")


def test_verification_gate_keeps_pipefail_enabled(project: Path) -> None:
    (project / ".claude/project-commands.json").write_text(
        json.dumps({"test": "false | true", "lint": None})
    )
    initial_commit = git(project, "rev-parse", "HEAD")

    result = run_loop(project, commit=True)

    assert result.returncode == 0, result.stderr
    assert "GATE FAILED: Tests did not pass" in result.stdout
    assert git(project, "rev-parse", "HEAD") == initial_commit
    assert not (project / "changed.txt").exists()
    assert_outcome(project, "reverted", "REVERT", journal_outcome="REVERT_TESTS")
