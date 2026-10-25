"""Verify read-only stop checks and event-specific hook output contracts."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(project: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(project), *args], text=True
    ).strip()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project = tmp_path / "project with spaces"
    project.mkdir()
    (project / ".gitignore").write_text(".claude/\n")
    git(project, "init", "--quiet", "-b", "main")
    git(project, "config", "user.name", "Test")
    git(project, "config", "user.email", "test@example.com")
    return project


def executable(path: Path, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env python3\n" + code)
    path.chmod(0o755)


def invoke(
    project: Path, script: str, payload: object, **variables: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash" if script.endswith(".sh") else "python3",
            str(ROOT / "hooks" / script),
        ],
        cwd=project,
        input=json.dumps(payload),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), **variables},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def tool_environment(
    project: Path, language: str, *, fail_format: bool = False, mutate: bool = False
) -> dict[str, str]:
    tool = project.parent / "bin" / ("uv" if language == "python" else "mix")
    executable(
        tool,
        """import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["TEST_CALLS"], "a") as stream:
    stream.write(json.dumps(args) + "\\n")
if "format" in args:
    if "--check" not in args and "--check-formatted" not in args:
        pathlib.Path(os.environ["TEST_SOURCE"]).write_text("rewritten")
    if os.environ["TEST_MUTATE"] == "true":
        pathlib.Path(os.environ["TEST_SOURCE"]).write_text("unexpected mutation")
    if os.environ["TEST_FAIL_FORMAT"] == "true":
        print("would reformat source")
        sys.exit(1)
""",
    )
    return {
        "PATH": f"{tool.parent}{os.pathsep}{os.environ['PATH']}",
        "TEST_CALLS": str(project.parent / "calls.jsonl"),
        "TEST_SOURCE": str(
            project
            / (
                "source 'with spaces'.py"
                if language == "python"
                else "source 'with spaces'.ex"
            )
        ),
        "TEST_FAIL_FORMAT": str(fail_format).lower(),
        "TEST_MUTATE": str(mutate).lower(),
    }


def setup_source(project: Path, language: str) -> Path:
    (project / ("pyproject.toml" if language == "python" else "mix.exs")).touch()
    source = project / (
        "source 'with spaces'.py" if language == "python" else "source 'with spaces'.ex"
    )
    source.write_text("original\n")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Committed code must be checked")
    return source


@pytest.mark.parametrize("language", ["python", "elixir"])
def test_stop_checks_committed_files_on_main_without_rewriting(
    project: Path, language: str
) -> None:
    source = setup_source(project, language)
    environment = tool_environment(project, language, fail_format=True)
    revision = git(project, "rev-parse", "HEAD")
    before = source.read_bytes()
    result = invoke(
        project, "lint-on-stop.sh", {"session_id": "fixture"}, **environment
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "block"
    assert "would reformat source" in json.loads(result.stdout)["reason"]
    assert source.read_bytes() == before
    assert git(project, "status", "--porcelain") == ""
    calls = [
        json.loads(line)
        for line in Path(environment["TEST_CALLS"]).read_text().splitlines()
    ]
    format_call = next(call for call in calls if "format" in call)
    assert source.name in format_call
    assert ("--check" if language == "python" else "--check-formatted") in format_call
    if language == "python":
        assert "--no-fix" in next(call for call in calls if "check" in call)
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["checked"]["revision"] == revision
    assert record["checked"]["scope"] == "revision"
    assert record["checked"] == record["after"]
    assert record["status"] == "failed"


@pytest.mark.parametrize("state", ["clean", "staged", "unstaged", "untracked"])
def test_verification_identifies_the_checked_revision_and_worktree(
    project: Path, state: str
) -> None:
    source = setup_source(project, "python")
    if state in ("staged", "unstaged"):
        source.write_text("dirty\n")
    if state == "staged":
        git(project, "add", source.name)
    if state == "untracked":
        (project / "untracked.py").write_text("new\n")
    environment = tool_environment(project, "python")
    result = invoke(project, "lint-on-stop.sh", {}, **environment)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == "passed"
    assert record["checked"]["scope"] == (
        "revision" if state == "clean" else "worktree"
    )
    assert record["checked"] == record["after"]


def test_mutation_during_verification_invalidates_the_result(project: Path) -> None:
    setup_source(project, "python")
    environment = tool_environment(project, "python", mutate=True)
    result = invoke(project, "lint-on-stop.sh", {}, **environment)
    assert json.loads(result.stdout)["decision"] == "block"
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == "changed"
    assert record["checked"] != record["after"]


@pytest.mark.parametrize("payload", [[], None])
def test_invalid_or_recursive_stop_input_does_no_work(
    project: Path, payload: object
) -> None:
    setup_source(project, "python")
    environment = tool_environment(project, "python")
    result = invoke(project, "lint-on-stop.sh", payload, **environment)
    assert result.returncode == 0
    assert result.stdout == ""
    assert not Path(environment["TEST_CALLS"]).exists()


def test_correction_turn_rechecks_changed_inputs_and_can_pass(project: Path) -> None:
    source = setup_source(project, "python")
    environment = tool_environment(project, "python", fail_format=True)
    first = invoke(project, "lint-on-stop.sh", {"session_id": "retry"}, **environment)
    assert json.loads(first.stdout)["decision"] == "block"
    source.write_text("corrected source\n")
    environment["TEST_FAIL_FORMAT"] = "false"
    second = invoke(
        project,
        "lint-on-stop.sh",
        {"session_id": "retry", "stop_hook_active": True},
        **environment,
    )
    assert second.stdout == ""
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == "passed"
    assert record["attempt"] == 2
    calls = Path(environment["TEST_CALLS"]).read_text()
    third = invoke(
        project,
        "lint-on-stop.sh",
        {"session_id": "retry", "stop_hook_active": True},
        **environment,
    )
    assert third.stdout == ""
    assert Path(environment["TEST_CALLS"]).read_text() == calls
    # An earlier success does not verify a subsequent committed change.
    source.write_text("new source\n")
    git(project, "add", source.name)
    git(project, "commit", "--quiet", "-m", "New revision")
    fourth = invoke(
        project,
        "lint-on-stop.sh",
        {"session_id": "retry", "stop_hook_active": True},
        **environment,
    )
    assert fourth.stdout == ""
    assert Path(environment["TEST_CALLS"]).read_text() != calls


def test_failed_corrections_have_bounded_retries_and_explicit_blocked_result(
    project: Path,
) -> None:
    setup_source(project, "python")
    environment = tool_environment(project, "python", fail_format=True)
    for attempt in range(3):
        result = invoke(
            project,
            "lint-on-stop.sh",
            {"session_id": "retry", "stop_hook_active": attempt > 0},
            **environment,
        )
        assert json.loads(result.stdout)["decision"] == "block"
    calls = Path(environment["TEST_CALLS"]).read_text()
    blocked = invoke(
        project,
        "lint-on-stop.sh",
        {"session_id": "retry", "stop_hook_active": True},
        **environment,
    )
    output = json.loads(blocked.stdout)
    assert output["continue"] is False
    assert "blocked after three attempts" in output["stopReason"]
    assert Path(environment["TEST_CALLS"]).read_text() == calls
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == "blocked"
    # A new user turn may retry after repairing infrastructure or configuration.
    environment["TEST_FAIL_FORMAT"] = "false"
    assert (
        invoke(
            project, "lint-on-stop.sh", {"session_id": "retry"}, **environment
        ).stdout
        == ""
    )


@pytest.mark.parametrize("credo_exit", [0, 1, 2, 127])
@pytest.mark.parametrize("diff_fails", [False, True])
def test_ship_gate_delivers_credo_failure_as_a_block(
    project: Path, credo_exit: int, diff_fails: bool
) -> None:
    (project / "mix.exs").write_text("initial\n")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Initial")
    git(project, "checkout", "--quiet", "-b", "feature")
    (project / "changed 'with spaces'.ex").write_text("changed\n")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Implementation")
    (project / ".claude").mkdir()
    (project / ".claude/pr-description.md").write_text(
        "<!-- user-approved -->\nFixture\n"
    )
    tool = project.parent / "bin/mix"
    executable(
        tool,
        f"import json, sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit({credo_exit})\n",
    )
    if diff_fails:
        executable(
            tool.parent / "git",
            f"import os, sys\nif 'diff' in sys.argv: sys.exit(7)\nos.execv({shutil.which('git')!r}, sys.argv)\n",
        )
    result = invoke(
        project,
        "ship-gate.sh",
        {
            "tool_name": "Bash",
            "tool_input": {"command": 'gh pr create --title "Fixture"'},
        },
        PATH=f"{tool.parent}{os.pathsep}{os.environ['PATH']}",
    )
    assert result.returncode == (0 if credo_exit == 0 and not diff_fails else 2)
    if diff_fails:
        assert "BLOCKED: ship-gate failed" in result.stderr
    elif credo_exit:
        assert "BLOCKED: Credo found issues" in result.stderr
        assert "changed 'with spaces'.ex" in result.stderr


def test_style_warnings_use_post_tool_context(project: Path) -> None:
    (project / "pyproject.toml").touch()
    result = invoke(
        project,
        "python-style-check.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(project / "source.py"),
                "new_string": "@staticmethod\ndef bad(): pass",
            },
        },
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "PostToolUse"
    assert "staticmethod" in output["additionalContext"]


def test_failed_tool_audit_records_current_failure_payload(project: Path) -> None:
    result = invoke(
        project,
        "audit-logger.py",
        {
            "hook_event_name": "PostToolUseFailure",
            "session_id": "test",
            "tool_name": "Bash",
            "tool_input": {"command": "false"},
            "error": "Exit code 1\nfailed",
            "is_interrupt": False,
        },
    )
    assert result.returncode == 0
    assert result.stdout == ""
    entry = json.loads((project / ".claude/logs/tool-calls.jsonl").read_text())
    assert entry["event"] == "PostToolUseFailure"
    assert entry["error"] == "Exit code 1\nfailed"
    assert entry["is_interrupt"] is False


@pytest.mark.parametrize(
    "error",
    [
        "overloaded",
        "authentication_failed",
        "oauth_org_not_allowed",
        "account_on_hold",
        "cloud_credential_error",
        "future_error",
    ],
)
def test_stop_failure_is_observable_without_claiming_recovery(
    project: Path, error: str
) -> None:
    result = invoke(
        project,
        "stop-failure-logger.sh",
        {
            "hook_event_name": "StopFailure",
            "cwd": str(project),
            "session_id": "test",
            "error": error,
            "error_details": 'quoted "detail"\nnext line',
            "last_assistant_message": "API Error: failed",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    entry = json.loads((project / ".claude/logs/stop-failures.jsonl").read_text())
    assert entry["error"] == error
    assert entry["error_details"] == 'quoted "detail"\nnext line'
    assert entry["last_assistant_message"] == "API Error: failed"


def test_toast_uses_current_message_and_passes_it_as_data(project: Path) -> None:
    tool = project.parent / "bin/osascript"
    output = project.parent / "notification.json"
    executable(
        tool,
        'import json, os, sys\nfrom pathlib import Path\nPath(os.environ["TEST_NOTIFICATION"]).write_text(json.dumps(sys.argv[1:]))\n',
    )
    result = invoke(
        project,
        "toast-notify.sh",
        {
            "last_assistant_message": 'Current "response"',
            "transcript_path": "missing.jsonl",
        },
        PATH=f"{tool.parent}{os.pathsep}{os.environ['PATH']}",
        TEST_NOTIFICATION=str(output),
    )
    assert result.returncode == 0
    assert json.loads(output.read_text())[-1] == 'Current "response"'


def test_formatting_is_an_explicit_mutating_action(project: Path) -> None:
    source = setup_source(project, "python")
    environment = tool_environment(project, "python")
    result = subprocess.run(
        [str(ROOT / "scripts/format-project.sh"), str(project)],
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert source.read_text() == "rewritten"


def test_infrastructure_failure_records_incomplete_and_returns_valid_json(
    project: Path,
) -> None:
    setup_source(project, "python")
    environment = tool_environment(project, "python")
    tool = project.parent / "bin/uv"
    tool.write_text(
        tool.read_text()
        + '\nif "pytest" in args:\n    print("Connection refused")\n    sys.exit(1)\n'
    )
    result = invoke(project, "lint-on-stop.sh", {}, **environment)
    assert result.returncode == 0, result.stderr
    assert "incomplete" in json.loads(result.stdout)["systemMessage"]
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == "incomplete"


def test_head_change_during_checks_cannot_verify_a_different_revision(
    project: Path,
) -> None:
    setup_source(project, "python")
    revision = git(project, "rev-parse", "HEAD")
    environment = tool_environment(project, "python")
    tool = project.parent / "bin/uv"
    tool.write_text(
        tool.read_text()
        + '\nif "format" in args:\n    import subprocess\n    subprocess.run(["git", "commit", "--quiet", "--allow-empty", "-m", "Changed HEAD"], check=True)\n'
    )
    result = invoke(project, "lint-on-stop.sh", {}, **environment)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "block"
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["checked"]["revision"] == revision
    assert record["after"]["revision"] != revision
    assert record["status"] == "changed"


def test_state_capture_failure_replaces_an_earlier_success(project: Path) -> None:
    setup_source(project, "python")
    environment = tool_environment(project, "python")
    assert invoke(project, "lint-on-stop.sh", {}, **environment).returncode == 0
    record_path = next((project / ".claude/verification").glob("*.json"))
    assert json.loads(record_path.read_text())["status"] == "passed"
    tool = project.parent / "bin/uv"
    tool.write_text(
        tool.read_text()
        + '\nif "format" in args:\n    pathlib.Path(".git").rename(".git-unavailable")\n'
    )
    result = invoke(project, "lint-on-stop.sh", {}, **environment)
    assert result.returncode == 0
    assert json.loads(record_path.read_text())["status"] == "unavailable"
