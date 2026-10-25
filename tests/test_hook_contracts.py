"""Verify read-only stop checks and event-specific hook output contracts."""

import json
import os
import re
import shlex
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


def invoke_event(
    project: Path, event: str, payload: dict
) -> list[subprocess.CompletedProcess[str]]:
    registrations = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
    results = []
    for group in registrations.get(event, []):
        if not re.fullmatch(group.get("matcher", ".*"), payload["tool_name"]):
            continue
        for hook in group["hooks"]:
            if hook["type"] == "command":
                command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))
                results.append(
                    subprocess.run(
                        shlex.split(command),
                        cwd=project,
                        input=json.dumps(payload),
                        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=10,
                    )
                )
    return results


@pytest.mark.parametrize(
    "command",
    [
        "pip install example",
        "black .",
        "mypy .",
        "python script.py",
        "gh pr create --title 'Final change'",
        "git push origin feature",
    ],
)
def test_global_hooks_allow_project_python_tools_and_publishing_without_a_marker(
    project: Path, command: str
) -> None:
    (project / "pyproject.toml").touch()
    results = invoke_event(
        project,
        "PreToolUse",
        {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        },
    )
    assert results
    assert all(result.returncode == 0 for result in results)
    assert all(result.stdout == "" for result in results)


def test_global_edit_hooks_do_not_infer_pydantic_apis(project: Path) -> None:
    (project / "pyproject.toml").touch()
    results = invoke_event(
        project,
        "PostToolUse",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "source.py",
                "content": "class Config: pass\nresult = unrelated.dict()\n",
            },
        },
    )
    assert results
    assert all(result.returncode == 0 and result.stdout == "" for result in results)


@pytest.mark.parametrize("mode", ["0", "1"])
def test_ralph_plan_update_gate_is_active_only_for_builds(
    project: Path, mode: str
) -> None:
    (project / "IMPLEMENTATION_PLAN.md").write_text("- [ ] Task\n")
    (project / "code.txt").write_text("before\n")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Initial")
    base = git(project, "rev-parse", "HEAD")
    (project / "code.txt").write_text("after\n")
    git(project, "commit", "--quiet", "-am", "Implement without plan update")
    result = invoke(
        project,
        "ralph-on-stop.sh",
        {"stop_hook_active": False},
        RALPH_MODE=mode,
        RALPH_PRE_COMMIT=base,
    )
    assert result.returncode == 0, result.stderr
    if mode == "1":
        assert json.loads(result.stdout)["decision"] == "block"
        assert "IMPLEMENTATION_PLAN.md was not updated" in result.stdout
    else:
        assert result.stdout == ""


def test_ralph_quality_judge_does_not_reenter_build_hook(project: Path) -> None:
    (project / "IMPLEMENTATION_PLAN.md").write_text("- [ ] Task\n")
    (project / "code.txt").write_text("before\n")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Initial")
    base = git(project, "rev-parse", "HEAD")
    (project / "IMPLEMENTATION_PLAN.md").write_text("- [x] Task\n")
    (project / "code.txt").write_text("after\n")
    git(project, "commit", "--quiet", "-am", "Implement and update plan")
    executable(
        project.parent / "bin/claude",
        """
import os
from pathlib import Path
Path(os.environ["TEST_JUDGE_MODE"]).write_text(os.environ.get("RALPH_MODE", ""))
print("PASS")
""",
    )
    mode_file = project.parent / "judge-mode"
    result = invoke(
        project,
        "ralph-on-stop.sh",
        {"stop_hook_active": False},
        RALPH_MODE="1",
        RALPH_PRE_COMMIT=base,
        TEST_JUDGE_MODE=str(mode_file),
        PATH=f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert mode_file.read_text() == "0"


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
    if language == "python":
        (project / ".claude").mkdir(exist_ok=True)
        (project / ".claude/project-commands.json").write_bytes(
            (
                ROOT / "profiles/python/uv-ruff-basedpyright/project-commands.json"
            ).read_bytes()
        )
    source = project / (
        "source 'with spaces'.py" if language == "python" else "source 'with spaces'.ex"
    )
    source.write_text("original\n")
    git(project, "add", ".")
    if language == "python":
        git(project, "add", "--force", ".claude/project-commands.json")
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
    assert ("." if language == "python" else source.name) in format_call
    assert ("--check" if language == "python" else "--check-formatted") in format_call
    assert all("--fix" not in call for call in calls)
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
    calls = [
        json.loads(line)
        for line in Path(environment["TEST_CALLS"]).read_text().splitlines()
    ]
    assert "--no-fix" in next(call for call in calls if "check" in call)
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


@pytest.mark.parametrize("commands", [None, {}, {"lint": None, "test": ""}])
def test_python_stop_and_format_do_not_select_tools_implicitly(
    project: Path, commands: dict | None
) -> None:
    setup_source(project, "python")
    configuration = project / ".claude/project-commands.json"
    if commands is None:
        configuration.unlink()
    else:
        configuration.write_text(json.dumps(commands))
    environment = tool_environment(project, "python")
    result = invoke(project, "lint-on-stop.sh", {}, **environment)
    assert result.returncode == 0 and result.stdout == ""
    assert not (project / ".claude/verification").exists()
    formatted = subprocess.run(
        [str(ROOT / "scripts/format-project.sh"), str(project)],
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
    )
    assert formatted.returncode == 0, formatted.stderr
    assert not Path(environment["TEST_CALLS"]).exists()


@pytest.mark.parametrize("failed_tool", ["black", "mypy", "pytest", None])
def test_python_stop_uses_configured_black_mypy_and_test_commands(
    project: Path, failed_tool: str | None
) -> None:
    setup_source(project, "python")
    (project / ".claude/project-commands.json").write_text(
        json.dumps(
            {
                "lint": "black --check . && mypy .",
                "test": "python -m pytest --label 'two spaces' | cat",
            }
        )
    )
    tool_dir = project.parent / "bin"
    for tool in ("black", "mypy", "python"):
        executable(
            tool_dir / tool,
            """
import json, os, sys
from pathlib import Path
with open(os.environ["TEST_CALLS"], "a") as stream:
    stream.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + "\\n")
sys.exit(1 if os.environ["TEST_FAILED_TOOL"] in [Path(sys.argv[0]).name, *sys.argv[1:]] else 0)
""",
        )
    calls_file = project.parent / "calls.jsonl"
    result = invoke(
        project,
        "lint-on-stop.sh",
        {},
        PATH=f"{tool_dir}{os.pathsep}{os.environ['PATH']}",
        TEST_CALLS=str(calls_file),
        TEST_FAILED_TOOL=failed_tool or "none",
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
    assert calls[0] == ["black", "--check", "."]
    assert ["python", "-m", "pytest", "--label", "two spaces"] in calls
    if failed_tool != "black":
        assert ["mypy", "."] in calls
    if failed_tool:
        assert json.loads(result.stdout)["decision"] == "block"
    else:
        assert result.stdout == ""


def test_invalid_python_commands_block_instead_of_skipping(project: Path) -> None:
    setup_source(project, "python")
    (project / ".claude/project-commands.json").write_text('{"lint": false}')
    result = invoke(project, "lint-on-stop.sh", {})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "block"
    assert "project-commands.json" in result.stdout


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
