"""Check Ralph's process statuses through the loop's recorded outcomes."""

import csv
import json
import os
import pty
import selectors
import time
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LOOP = Path("skills/ralph/scripts/loop.sh")
EVALUATION = {
    "verdict": "ACCEPT",
    "scores": {
        name: 4
        for name in (
            "spec_fidelity",
            "correctness",
            "integration_quality",
            "code_quality",
            "test_coverage",
            "compression",
        )
    },
    "average": 4,
    "criteria_results": [
        {
            "criterion": "Fixture requirement",
            "result": "PASS",
            "notes": "Verified fixture evidence",
        }
    ],
    "issues": [],
    "summary": "Full run report",
    "revise_guidance": "",
}


def single_worktree(project: Path) -> Path:
    evaluated = project / ".claude/evaluated-path"
    if evaluated.exists():
        return Path(evaluated.read_text().strip())
    return next((project / ".claude/worktrees").glob("status-test-*"))


def single_branch(project: Path) -> str:
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    return f"ralph-status-test/{run.name}"


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
        Path("skills/ralph/scripts/options.sh"),
        Path("skills/ralph/scripts/orchestrate-parallel.sh"),
        Path("skills/ralph/scripts/merge-workers.sh"),
        Path("skills/ralph/references/PROMPT_build.md"),
        Path("skills/ralph/references/PROMPT_evaluate.md"),
        Path("scripts/lib/parallel-primitives.sh"),
        Path("scripts/lib/worktree-safety.sh"),
        Path("scripts/lib/claude-runner.sh"),
        Path("scripts/evaluate.py"),
        Path("hooks/verification-state.py"),
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
        'printf "%s" "${RALPH_MODE:-}" > "$CLAUDE_PROJECT_DIR/ralph-mode.txt"\n'
        'if [ "$TEST_COMMIT" = true ]; then\n'
        '  printf "change\\n" > changed.txt\n'
        "  git add changed.txt\n"
        '  git commit --quiet -m "Implement task"\n'
        "fi\n"
        'printf "Claude output\\n"\n'
        'printf "Claude diagnostic\\n" >&2\n'
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
    (project_dir / ".gitignore").write_text(".claude/\nprompt.txt\nralph-mode.txt\n")
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
    assert (project / "ralph-mode.txt").read_text() == "1"

    assert result.returncode == (0 if claude_exit == 0 else 1), result.stderr
    outcome = "success" if claude_exit == 0 else f"error (code {claude_exit})"
    assert_outcome(
        project, outcome, "NO_COMMIT" if claude_exit == 0 else "ERROR_PIPELINE"
    )
    assert "Stream processor exited" not in result.stderr
    if claude_exit != 0:
        assert "error (code 7)" in result.stderr
        assert "completed successfully" not in result.stdout


def test_timeout_reaches_recorded_outcomes(project: Path) -> None:
    if shutil.which("timeout") is None and shutil.which("gtimeout") is None:
        pytest.skip("GNU timeout is required")

    result = run_loop(project, time_budget="1", hang=True)

    assert result.returncode == 1, result.stderr
    assert "timeout" in result.stderr
    assert "completed successfully" not in result.stdout
    assert "Stream processor exited" not in result.stderr
    assert_outcome(project, "timeout", "TIMEOUT")


@pytest.mark.parametrize("claude_exit", [0, 7])
def test_processor_failure_is_not_success_and_retains_all_statuses(
    project: Path, claude_exit: int
) -> None:
    result = run_loop(project, claude_exit=claude_exit, processor_exit=9)
    assert result.returncode == 1, result.stderr
    outcome = (
        "processor error (code 9)"
        if claude_exit == 0
        else f"error (code {claude_exit})"
    )
    assert_outcome(project, outcome, "ERROR_PIPELINE")
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    status = json.loads(next(run.glob("iter-*.status.json")).read_text())
    assert status == {
        "prompt_exit": 0,
        "claude_exit": claude_exit,
        "processor_exit": 9,
        "outcome": outcome,
    }
    assert (
        next(run.glob("iter-*.claude-stderr.log")).read_text() == "Claude diagnostic\n"
    )


@pytest.mark.parametrize("failure", ["claude", "processor", "timeout"])
def test_failed_pipeline_preserves_commits_without_accepting_them(
    project: Path, failure: str
) -> None:
    original = git(project, "rev-parse", "HEAD")
    result = run_loop(
        project,
        commit=True,
        claude_exit=7 if failure == "claude" else 0,
        processor_exit=9 if failure == "processor" else 0,
        time_budget="1" if failure == "timeout" else "0",
        hang=failure == "timeout",
    )
    assert result.returncode == 1
    assert git(project, "rev-parse", "HEAD") != original
    assert (project / "changed.txt").exists()
    marker = json.loads((project / ".claude/ralph-worker-done-test-worker").read_text())
    assert marker["status"] == "error"
    trace = next((project / ".claude/ralph/status-test/runs").glob("*/trace.jsonl"))
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert not any(event.get("outcome") == "KEEP" for event in events)


def test_prompt_producer_failure_is_recorded(project: Path) -> None:
    write_executable(project.parent / "bin/claude", "cat >/dev/null\n")
    log = project / ".claude/producer.log"
    library = project.parent / "plugin with spaces/scripts/lib/claude-runner.sh"
    processor = (
        project.parent / "plugin with spaces/skills/ralph/scripts/stream-processor.py"
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            """set -euo pipefail
source "$1"
printf() { echo "producer failed" >&2; return 13; }
if run_claude_pipeline prompt "$2" "$3" 0 "$4" -p; then exit 99; fi
""",
            "test",
            str(library),
            str(log),
            str(log.with_suffix(".jsonl")),
            str(processor),
        ],
        cwd=project,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "TEST_PROCESSOR_EXIT": "0",
        },
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    status = json.loads(Path(str(log) + ".status.json").read_text())
    assert status == {
        "prompt_exit": 13,
        "claude_exit": 0,
        "processor_exit": 0,
        "outcome": "prompt error (code 13)",
    }
    assert "producer failed" in Path(str(log) + ".prompt-stderr.log").read_text()


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
    during_confirmation: str = "",
    per_iteration: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Supply a real TTY so an unsafe merge prompt would actually merge."""
    write_executable(
        project.parent / "bin/claude",
        r"""
prompt=$(cat)
if [[ " $* " == *' --json-schema '* ]]; then
  echo evaluate >> "$TEST_ROOT_PROJECT/.claude/order"
  pwd > "$TEST_ROOT_PROJECT/.claude/evaluated-path"
  case "$TEST_EVAL_VERDICT" in
    missing) ;;
    malformed) echo '{invalid' ;;
    incomplete) echo '{"subtype":"success","is_error":false,"structured_output":{"verdict":"ACCEPT"}}' ;;
    timeout) sleep 30 ;;
    *) python3 - <<'PYRESULT'
import json, os
payload = json.loads(os.environ["TEST_VALID_EVALUATION"])
payload["verdict"] = os.environ["TEST_EVAL_VERDICT"]
if payload["verdict"] == "REVISE":
    payload["scores"] = {key: 2 for key in payload["scores"]}
    payload["average"] = 2
    payload["revise_guidance"] = "Correct the fixture behavior"
print(json.dumps({"subtype": "success", "is_error": False, "structured_output": payload}))
PYRESULT
    ;;
  esac
  if [ "$TEST_AFTER_EVAL" = target ]; then
    git -C "$TEST_ROOT_PROJECT" commit --quiet --allow-empty -m 'Target diverged during evaluation'
  elif [ -n "$TEST_AFTER_EVAL" ]; then
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
                "RALPH_EVAL_PER_ITER": str(per_iteration).lower(),
                "RALPH_EVAL_DIFF_THRESHOLD": "1",
                "RALPH_EVAL_TIMEOUT": "1" if verdict == "timeout" else "10",
                "AUTO_HARVEST": "false",
                "TEST_PROCESSOR_EXIT": "0",
                "TEST_VALID_EVALUATION": json.dumps(EVALUATION),
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
        prefix_out, prefix_err = "", ""
        if during_confirmation:
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            captured = {"stdout": b"", "stderr": b""}
            deadline = time.monotonic() + 10
            try:
                while b"now? [y/N]" not in captured["stdout"] + captured["stderr"]:
                    assert time.monotonic() < deadline, captured
                    for key, _ in selector.select(timeout=0.2):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        captured[key.data] += chunk
                worktree = single_worktree(project)
                if during_confirmation == "target":
                    git(
                        project,
                        "commit",
                        "--quiet",
                        "--allow-empty",
                        "-m",
                        "Target changed",
                    )
                elif during_confirmation == "guidance":
                    (worktree / ".claude/project-commands.json").write_text(
                        '{"test":"false"}'
                    )
                else:
                    (worktree / "unverified.txt").write_text("not evaluated")
                    if during_confirmation == "commit":
                        git(worktree, "add", "unverified.txt")
                        git(worktree, "commit", "--quiet", "-m", "Unverified change")
                prefix_out, prefix_err = (
                    captured["stdout"].decode(),
                    captured["stderr"].decode(),
                )
            finally:
                selector.close()
        os.write(master, b"y\n")
        stdout, stderr = process.communicate(timeout=15)
        stdout, stderr = prefix_out + stdout, prefix_err + stderr
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
    assert not single_worktree(project).exists()
    order = (project / ".claude/order").read_text().splitlines()
    assert order == ["verify", "verify", "evaluate"]
    evaluated_path = (project / ".claude/evaluated-path").read_text().strip()
    assert evaluated_path == str(single_worktree(project))
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    assert json.loads((run / "eval-verdict.json").read_text())["verdict"] == "ACCEPT"
    assert json.loads((run / "eval-verdict.json").read_text())["revision"] == git(
        project, "rev-parse", "HEAD"
    )
    assert "Full run report" in (run / "eval-summary.md").read_text()
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

    assert result.returncode == (0 if verdict == "REVISE" else 1), result.stderr
    assert "EVAL GATE: Merge blocked" in result.stdout
    assert git(project, "rev-parse", "HEAD") == initial_commit
    worktree = single_worktree(project)
    assert (worktree / "changed.txt").exists()
    assert git(project, "rev-parse", single_branch(project)) != initial_commit


@pytest.mark.parametrize(("evaluate", "once"), [(False, False), (True, True)])
def test_skipped_end_of_run_evaluation_cannot_satisfy_gate(
    project: Path, evaluate: bool, once: bool
) -> None:
    result = run_single_track(project, evaluate=evaluate, once=once)

    assert result.returncode == 0, result.stderr
    assert "EVAL GATE: Merge blocked" in result.stdout
    assert not (project / "changed.txt").exists()
    assert (single_worktree(project) / "changed.txt").exists()


@pytest.mark.parametrize("after_eval", ["dirty", "commit"])
def test_accept_cannot_merge_work_changed_after_verification(
    project: Path, after_eval: str
) -> None:
    result = run_single_track(project, after_eval=after_eval)

    assert result.returncode == 1, result.stderr
    assert "Merge blocked: worktree changed" in result.stdout
    assert not (project / "changed.txt").exists()
    assert (single_worktree(project) / "after-eval.txt").exists()


@pytest.mark.parametrize("change", ["commit", "dirty", "target", "guidance"])
def test_merge_confirmation_cannot_accept_changed_candidate_or_target(
    project: Path, change: str
) -> None:
    original = git(project, "rev-parse", "HEAD")
    result = run_single_track(project, during_confirmation=change)
    assert result.returncode == 1, result.stdout + result.stderr
    assert not (project / "changed.txt").exists()
    assert not (project / "unverified.txt").exists()
    assert single_worktree(project).exists()
    if change != "target":
        assert git(project, "rev-parse", "HEAD") == original


def test_diverged_target_cannot_create_an_unverified_merge_commit(
    project: Path,
) -> None:
    result = run_single_track(project, after_eval="target")
    assert result.returncode == 1, result.stdout + result.stderr
    assert not (project / "changed.txt").exists()
    assert (single_worktree(project) / "changed.txt").exists()
    assert "Merge failed or target checkout changed" in result.stdout


def test_repeated_runs_preserve_old_work_and_create_unique_worktrees(
    project: Path,
) -> None:
    first = run_single_track(project, verdict="REVISE")
    assert first.returncode == 0
    old = single_worktree(project)
    old_head = git(old, "rev-parse", "HEAD")
    second = run_single_track(project, verdict="REVISE")
    assert second.returncode == 0, second.stderr
    assert single_worktree(project) != old
    assert git(old, "rev-parse", "HEAD") == old_head
    assert len(list((project / ".claude/worktrees").iterdir())) == 2


def test_iteration_evaluation_error_is_not_accepted_or_overwritten(
    project: Path,
) -> None:
    result = run_single_track(project, per_iteration=True, verdict="missing")
    assert result.returncode == 1, result.stdout + result.stderr
    assert (single_worktree(project) / "changed.txt").exists()
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    assert json.loads((run / "eval-1-verdict.json").read_text())["verdict"] == "ERROR"
    assert json.loads((run / "eval-verdict.json").read_text())["verdict"] == "NOT_RUN"
    events = [
        json.loads(line) for line in (run / "trace.jsonl").read_text().splitlines()
    ]
    assert not any(event.get("outcome") == "KEEP" for event in events)


def test_zero_commit_cleanup_preserves_dirty_work(project: Path) -> None:
    result = run_single_track(project, commit=False)

    assert result.returncode == 0, result.stderr
    assert (single_worktree(project) / "unfinished.txt").read_text() == "unfinished\n"


def test_accept_cannot_bypass_failed_final_verification(project: Path) -> None:
    result = run_single_track(project, final_verification_failure=True)

    assert result.returncode == 1, result.stderr
    assert "Merge blocked: final verification failed" in result.stdout
    assert not (project / "changed.txt").exists()
    assert (single_worktree(project) / "changed.txt").exists()


def run_parallel(
    plugin: Path,
    project: Path,
    *,
    merge_succeeds=True,
    start_on_target=True,
    eval_case="ACCEPT",
    eval_mode="end",
    after_eval="",
    flags=(),
    merge_output=None,
    merge_exit=0,
) -> subprocess.CompletedProcess[str]:
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
if [[ " $* " == *' --json-schema '* ]]; then
  echo evaluate >> "$TEST_ROOT_PROJECT/.claude/order"
  python3 - <<'PYRESULT'
import json, os
mode = os.environ["TEST_EVAL_CASE"]
payload = json.loads(os.environ["TEST_VALID_EVALUATION"])
if mode == "timeout":
    import time
    time.sleep(30)
if mode == "malformed":
    print("{invalid")
elif mode == "incomplete":
    print(json.dumps({"subtype": "success", "is_error": False, "structured_output": {"verdict": "ACCEPT"}}))
elif mode != "missing":
    if mode == "REVISE":
        payload["verdict"] = "REVISE"
        payload["revise_guidance"] = "Correct fixture integration"
    print(json.dumps({"subtype": "success", "is_error": False, "structured_output": payload}))
PYRESULT
  if [ -n "$TEST_AFTER_EVAL" ]; then
    echo unverified > after-eval.txt
    if [ "$TEST_AFTER_EVAL" = commit ]; then
      git add after-eval.txt
      git commit --quiet -m 'Changed after verification'
    fi
  fi
  if [ "$TEST_EVAL_CASE" = nonzero ]; then exit 7; fi
else
  printf '%s' "${RALPH_MODE:-}" > "$TEST_ROOT_PROJECT/.claude/worker-mode"
  echo implementation > changed.txt
  git add changed.txt
  git commit --quiet -m Implementation
fi
""",
    )
    if merge_output is not None:
        write_executable(
            plugin / "skills/ralph/scripts/merge-workers.sh",
            'printf "%s\\n" "$TEST_MERGE_OUTPUT"\nexit "$TEST_MERGE_EXIT"\n',
        )
    elif not merge_succeeds:
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
            *flags,
        ],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "CLAUDE_PLUGIN_ROOT": str(plugin),
            "CLAUDE_PROJECT_DIR": str(project),
            "TEST_ROOT_PROJECT": str(project),
            "TEST_VALID_EVALUATION": json.dumps(EVALUATION),
            "TEST_MERGE_OUTPUT": merge_output or "",
            "TEST_MERGE_EXIT": str(merge_exit),
            "TEST_EVAL_CASE": eval_case,
            "TEST_AFTER_EVAL": after_eval,
            "RALPH_PARALLEL_EVAL": eval_mode,
            "RALPH_EVAL_TIMEOUT": "0.2" if eval_case == "timeout" else "5",
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

    return result


@pytest.mark.parametrize("merge_succeeds", [True, False])
@pytest.mark.parametrize("start_on_target", [True, False])
def test_parallel_cleanup_preserves_failed_merges_and_archives_successes(
    plugin: Path, project: Path, merge_succeeds: bool, start_on_target: bool
) -> None:
    result = run_parallel(
        plugin, project, merge_succeeds=merge_succeeds, start_on_target=start_on_target
    )
    assert result.returncode == (0 if merge_succeeds else 1), (
        result.stdout + result.stderr
    )
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    worktree = project / f".claude/worktrees/status-test-{run.name}-wave0-worker-0"
    branch = f"ralph-status-test/{run.name}/wave-0/worker-0"
    assert worktree.exists() is not merge_succeeds
    assert not (project / ".claude/ralph/status-test/orchestrator.pid").exists()
    if merge_succeeds:
        assert (project / "changed.txt").exists()
        assert (
            json.loads((run / "merge-results.json").read_text())[0]["status"]
            == "success"
        )
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
            run / f"worktree-artifacts/{worktree.name}/.claude/tmux-output.log"
        ).exists()
        assert (project / ".claude/order").read_text().splitlines()[-2:] == [
            "verify",
            "evaluate",
        ]
    else:
        assert (worktree / "changed.txt").exists()
        assert git(project, "branch", "--list", branch)
        assert "work preserved and dependent waves blocked" in result.stdout


@pytest.mark.parametrize("eval_mode", ["end", "wave"])
@pytest.mark.parametrize(
    "eval_case", ["missing", "malformed", "incomplete", "nonzero", "timeout"]
)
def test_parallel_evaluation_errors_preserve_work_and_block_completion(
    plugin: Path, project: Path, eval_mode: str, eval_case: str
) -> None:
    result = run_parallel(plugin, project, eval_mode=eval_mode, eval_case=eval_case)
    assert result.returncode == 1, result.stdout + result.stderr
    assert list((project / ".claude/worktrees").iterdir())
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    path = run / ("eval-verdict.json" if eval_mode == "end" else "wave0-eval-0.json")
    assert json.loads(path.read_text())["verdict"] == "ERROR"
    assert "Complete!" not in result.stdout


@pytest.mark.parametrize("after_eval", ["dirty", "commit"])
def test_parallel_final_candidate_changes_cannot_finish_successfully(
    plugin: Path, project: Path, after_eval: str
) -> None:
    result = run_parallel(plugin, project, after_eval=after_eval)
    assert result.returncode == 1, result.stdout + result.stderr
    assert (project / "after-eval.txt").exists()
    assert list((project / ".claude/worktrees").iterdir())
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    assert json.loads((run / "eval-verdict.json").read_text())["verdict"] == "ERROR"


def test_parallel_required_accept_gate_rejects_revise(
    plugin: Path, project: Path
) -> None:
    result = run_parallel(
        plugin, project, eval_case="REVISE", flags=("--eval-gates-merge",)
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert list((project / ".claude/worktrees").iterdir())


def test_parallel_options_reach_workers_and_disable_all_evaluators(
    plugin: Path, project: Path
) -> None:
    result = run_parallel(
        plugin,
        project,
        flags=(
            "--time-budget",
            "42",
            "--checkpoint-every",
            "2",
            "--no-eval",
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run = next((project / ".claude/ralph/status-test/runs").iterdir())
    output = next(
        (run / "worktree-artifacts").glob("*/.claude/tmux-output.log")
    ).read_text()
    assert "Time budget: 42s" in output
    assert "Checkpoint: every 2 iterations" in output
    assert (project / ".claude/worker-mode").read_text() == "1"
    assert "evaluate" not in (project / ".claude/order").read_text().splitlines()
    assert json.loads((run / "eval-verdict.json").read_text())["verdict"] == "NOT_RUN"


@pytest.mark.parametrize(
    ("output", "exit_code"),
    [("invalid JSON", 0), ('{"status":"success","merged":1,"failed":0}', 7)],
)
def test_parallel_merge_protocol_errors_preserve_work(
    plugin: Path, project: Path, output: str, exit_code: int
) -> None:
    result = run_parallel(plugin, project, merge_output=output, merge_exit=exit_code)
    assert result.returncode == 1, result.stdout + result.stderr
    assert list((project / ".claude/worktrees").iterdir())
    assert "End-of-run evaluation:" not in result.stdout
