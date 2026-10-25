"""Check Ralph's process statuses through the loop's recorded outcomes."""

import csv
import json
import os
import pty
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
        Path("skills/ralph/scripts/orchestrate-parallel.sh"),
        Path("skills/ralph/scripts/merge-workers.sh"),
        Path("skills/ralph/references/PROMPT_build.md"),
        Path("skills/ralph/references/PROMPT_evaluate.md"),
        Path("scripts/lib/parallel-primitives.sh"),
        Path("scripts/lib/worktree-safety.sh"),
        Path("scripts/project-commands.py"),
        Path("scripts/task-plan.py"),
        Path("scripts/stitch-traces.sh"),
        Path("scripts/stitch-traces.py"),
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


def test_loop_reads_structured_task_progress_and_selects_a_ready_task(
    project: Path,
) -> None:
    tasks = [
        {
            "id": 1,
            "name": "Foundation",
            "status": "done",
            "priority": "HIGH",
            "deps": [],
            "files": [],
        },
        {
            "id": 2,
            "name": "Pipeline status",
            "status": "pending",
            "priority": "HIGH",
            "deps": [1],
            "files": [],
        },
    ]
    (project / ".claude/specs/status-test/IMPLEMENTATION_PLAN.md").write_text(
        "## Task Index\n```json\n" + json.dumps({"tasks": tasks}) + "\n```\n## Tasks\n"
    )
    result = run_loop(project)
    assert result.returncode == 0, result.stderr
    assert_outcome(project, "success", "NO_COMMIT")
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    events = [
        json.loads(line) for line in (run / "trace.jsonl").read_text().splitlines()
    ]
    state = next(event for event in events if event["type"] == "plan_state")
    assert (state["total"], state["done"], state["remaining"]) == (2, 1, 1)


def run_single_track(
    project: Path,
    *,
    verdict: str = "ACCEPT",
    evaluator_exit: int = 0,
    evaluate: bool = True,
    once: bool = False,
    after_eval: str = "",
    commit: bool = True,
    final_verification_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Supply a real TTY so an unsafe merge prompt would actually merge."""
    write_executable(
        project.parent / "bin/claude",
        r"""
prompt=$(cat)
if [[ "$prompt" == *'**Evaluation mode:** END-OF-RUN'* ]]; then
  echo evaluate >> "$TEST_ROOT_PROJECT/.claude/order"
  pwd > "$TEST_ROOT_PROJECT/.claude/evaluated-path"
  verdict_file=$(printf '%s\n' "$prompt" | sed -n 's/^\*\*Verdict output:\*\* //p')
  summary_file=$(printf '%s\n' "$prompt" | sed -n 's/^\*\*Summary output:\*\* //p')
  case "$TEST_EVAL_VERDICT" in
    missing) ;;
    malformed) echo '{invalid' > "$verdict_file" ;;
    incomplete) echo '{"verdict":"ACCEPT"}' > "$verdict_file" ;;
    timeout) sleep 30 ;;
    *) printf '{"verdict":"%s","average":8}\n' "$TEST_EVAL_VERDICT" > "$verdict_file" ;;
  esac
  echo 'Full run report' > "$summary_file"
  if [ -n "$TEST_AFTER_EVAL" ]; then
    echo changed > after-eval.txt
    if [ "$TEST_AFTER_EVAL" = commit ]; then
      git add after-eval.txt
      git commit --quiet -m 'Changed after verification'
    fi
  fi
  exit "$TEST_EVAL_EXIT"
fi
# Simulate an old per-iteration ACCEPT. Skipped or failed end-of-run evaluation
# must not let this artifact satisfy the merge gate.
for run in "$PWD"/.claude/ralph/status-test/runs/*; do
  echo '{"verdict":"ACCEPT","average":10}' > "$run/eval-verdict.json"
done
if [ "$TEST_COMMIT" = true ]; then
  echo implementation > changed.txt
  git add changed.txt
  git commit --quiet -m 'Implementation'
else
  echo unfinished > unfinished.txt
fi
""",
    )
    test_command = 'echo verify >> "$TEST_ROOT_PROJECT/.claude/order"'
    if final_verification_failure:
        test_command += '\ntest "$(wc -l < "$TEST_ROOT_PROJECT/.claude/order")" -eq 1'
    (project / ".claude/project-commands.json").write_text(
        json.dumps({"test": test_command, "lint": None})
    )
    arguments = [
        "bash",
        str(project.parent / "plugin with spaces" / LOOP),
        str(project / ".claude/specs/status-test"),
        "build",
        "1",
        "--time-budget=0",
        "--eval-gates-merge",
    ]
    if once:
        arguments.append("--once")
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(
            arguments,
            cwd=project,
            env={
                **os.environ,
                "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
                "CLAUDE_PROJECT_DIR": str(project),
                "RALPH_WORKER_ID": "",
                "RALPH_NO_MERGE_PROMPT": "",
                "RALPH_NOTIFY": "false",
                "RALPH_EVAL_END_OF_RUN": str(evaluate).lower(),
                "RALPH_EVAL_TIMEOUT": "1" if verdict == "timeout" else "10",
                "AUTO_HARVEST": "false",
                "TEST_PROCESSOR_EXIT": "0",
                "TEST_EVAL_VERDICT": verdict,
                "TEST_EVAL_EXIT": str(evaluator_exit),
                "TEST_AFTER_EVAL": after_eval,
                "TEST_COMMIT": str(commit).lower(),
                "TEST_ROOT_PROJECT": str(project),
            },
            stdin=slave,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        os.write(master, b"y\n")
        stdout, stderr = process.communicate(timeout=15)
    finally:
        os.close(master)
        os.close(slave)
    return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)


def test_end_of_run_evaluation_precedes_merge_and_artifact_cleanup(
    project: Path,
) -> None:
    result = run_single_track(project)

    assert result.returncode == 0, result.stderr
    assert (project / "changed.txt").read_text() == "implementation\n"
    assert not (project / ".claude/worktrees/status-test").exists()
    order = (project / ".claude/order").read_text().splitlines()
    assert order == ["verify", "verify", "evaluate"]
    evaluated_path = (project / ".claude/evaluated-path").read_text().strip()
    assert evaluated_path == str(project / ".claude/worktrees/status-test")
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    assert json.loads((run / "eval-verdict.json").read_text())["verdict"] == "ACCEPT"
    assert (run / "eval-summary.md").read_text() == "Full run report\n"
    assert (
        run / "worktree-artifacts/.claude/specs/status-test/IMPLEMENTATION_PLAN.md"
    ).exists()


@pytest.mark.parametrize(
    ("verdict", "evaluator_exit"),
    [
        ("REVISE", 0),
        ("missing", 0),
        ("malformed", 0),
        ("incomplete", 0),
        ("ACCEPT", 7),
        ("timeout", 0),
    ],
)
def test_eval_gate_preserves_work_without_fresh_accept(
    project: Path, verdict: str, evaluator_exit: int
) -> None:
    initial_commit = git(project, "rev-parse", "HEAD")

    result = run_single_track(project, verdict=verdict, evaluator_exit=evaluator_exit)

    assert result.returncode == 0, result.stderr
    assert "EVAL GATE: Merge blocked" in result.stdout
    assert git(project, "rev-parse", "HEAD") == initial_commit
    worktree = project / ".claude/worktrees/status-test"
    assert (worktree / "changed.txt").exists()
    assert git(project, "rev-parse", "status-test") != initial_commit


@pytest.mark.parametrize(("evaluate", "once"), [(False, False), (True, True)])
def test_skipped_end_of_run_evaluation_cannot_satisfy_gate(
    project: Path, evaluate: bool, once: bool
) -> None:
    result = run_single_track(project, evaluate=evaluate, once=once)

    assert result.returncode == 0, result.stderr
    assert "EVAL GATE: Merge blocked" in result.stdout
    assert not (project / "changed.txt").exists()
    assert (project / ".claude/worktrees/status-test/changed.txt").exists()


@pytest.mark.parametrize("after_eval", ["dirty", "commit"])
def test_accept_cannot_merge_work_changed_after_verification(
    project: Path, after_eval: str
) -> None:
    result = run_single_track(project, after_eval=after_eval)

    assert result.returncode == 0, result.stderr
    assert "Merge blocked: worktree changed" in result.stdout
    assert not (project / "changed.txt").exists()
    assert (project / ".claude/worktrees/status-test/after-eval.txt").exists()


def test_zero_commit_cleanup_preserves_dirty_work(project: Path) -> None:
    result = run_single_track(project, commit=False)

    assert result.returncode == 0, result.stderr
    assert (
        project / ".claude/worktrees/status-test/unfinished.txt"
    ).read_text() == "unfinished\n"


def test_accept_cannot_bypass_failed_final_verification(project: Path) -> None:
    result = run_single_track(project, final_verification_failure=True)

    assert result.returncode == 0, result.stderr
    assert "Merge blocked: final verification failed" in result.stdout
    assert not (project / "changed.txt").exists()
    assert (project / ".claude/worktrees/status-test/changed.txt").exists()


@pytest.mark.parametrize("merge_succeeds", [True, False])
@pytest.mark.parametrize("start_on_target", [True, False])
def test_parallel_cleanup_preserves_failed_merges_and_archives_successes(
    plugin: Path, project: Path, merge_succeeds: bool, start_on_target: bool
) -> None:
    if start_on_target:
        git(project, "checkout", "--quiet", "-b", "status-test")
    write_executable(
        plugin / "skills/ralph/scripts/partition-tasks.sh",
        'echo \'{"workers":{"worker-0":[1]},"waves":[{"wave":0,"tasks":[1]}]}\'\n',
    )
    write_executable(
        project.parent / "bin/tmux",
        r"""
if [ "$1" = new-session ]; then
  launcher="${!#}"
  while [ "$#" -gt 1 ]; do
    if [ "$1" = -c ]; then working_dir="$2"; break; fi
    shift
  done
  (cd "$working_dir" && bash "$launcher") > "$working_dir/.claude/tmux-output.log" 2>&1
fi
""",
    )
    write_executable(
        project.parent / "bin/claude",
        r"""
prompt=$(cat)
if [[ "$prompt" == *'**Evaluation mode:** END-OF-RUN'* ]]; then
  echo evaluate >> "$TEST_ROOT_PROJECT/.claude/order"
  verdict_file=$(printf '%s\n' "$prompt" | sed -n 's/^\*\*Verdict output:\*\* //p')
  summary_file=$(printf '%s\n' "$prompt" | sed -n 's/^\*\*Summary output:\*\* //p')
  echo '{"verdict":"ACCEPT","average":8}' > "$verdict_file"
  echo report > "$summary_file"
else
  echo implementation > changed.txt
  git add changed.txt
  git commit --quiet -m Implementation
fi
""",
    )
    if not merge_succeeds:
        write_executable(
            plugin / "skills/ralph/scripts/merge-workers.sh",
            'echo \'{"status":"partial","merged":0,"failed":1}\'\n',
        )
    (project / ".claude/project-commands.json").write_text(
        json.dumps(
            {"test": 'echo verify >> "$TEST_ROOT_PROJECT/.claude/order"', "lint": None}
        )
    )

    result = subprocess.run(
        [
            "bash",
            str(plugin / "skills/ralph/scripts/orchestrate-parallel.sh"),
            str(project / ".claude/specs/status-test"),
            "status-test",
            "1",
            "1",
        ],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "CLAUDE_PLUGIN_ROOT": str(plugin),
            "CLAUDE_PROJECT_DIR": str(project),
            "TEST_ROOT_PROJECT": str(project),
            "TEST_PROCESSOR_EXIT": "0",
            "RALPH_WORKER_ID": "",
            "RALPH_NOTIFY": "false",
            "AUTO_HARVEST": "false",
            "TMUX": "",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    worktree = project / ".claude/worktrees/status-test-wave0-worker-0"
    branch = "ralph-status-test/wave-0/worker-0"
    assert worktree.exists() is not merge_succeeds
    assert not (project / ".claude/ralph/status-test/orchestrator.pid").exists()
    if merge_succeeds:
        assert (project / "changed.txt").exists()
        assert git(project, "branch", "--list", branch) == ""
        run = next((project / ".claude/ralph/status-test/runs").iterdir())
        unified = [
            json.loads(line)
            for line in (run / "unified-trace.jsonl").read_text().splitlines()
        ]
        assert any(event["source"] == "wave0-worker-0" for event in unified)
        assert any(
            event["type"] == "parallel_end" and event["source"] == "orchestrator"
            for event in unified
        )
        assert list((run / "worker-traces/wave0-worker-0").glob("*/trace.jsonl"))
        assert (run / "eval-verdict.json").exists()
        assert (
            run
            / "worktree-artifacts/status-test-wave0-worker-0/.claude/tmux-output.log"
        ).exists()
        assert (project / ".claude/order").read_text().splitlines()[-2:] == [
            "verify",
            "evaluate",
        ]
    else:
        assert (worktree / "changed.txt").exists()
        assert git(project, "branch", "--list", branch)
        assert "preserved 1" in result.stdout
