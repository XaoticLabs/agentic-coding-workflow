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
        env={
            **os.environ,
            "WORKFLOW_NOTIFY": "false",
            "CLAUDE_PROJECT_DIR": str(project),
            **variables,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def invoke_event(
    project: Path, event: str, payload: dict, **variables: str
) -> list[subprocess.CompletedProcess[str]]:
    registrations = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
    results = []
    for group in registrations.get(event, []):
        value = (
            payload.get("notification_type", "")
            if event == "Notification"
            else payload.get("tool_name", "")
        )
        if not re.fullmatch(group.get("matcher", ".*"), value):
            continue
        for hook in group["hooks"]:
            if hook["type"] == "command":
                command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))
                results.append(
                    subprocess.run(
                        shlex.split(command),
                        cwd=project,
                        input=json.dumps({"hook_event_name": event, **payload}),
                        env={
                            **os.environ,
                            "WORKFLOW_NOTIFY": "false",
                            "CLAUDE_PROJECT_DIR": str(project),
                            **variables,
                        },
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=10,
                    )
                )
    return results


@pytest.fixture
def desktop(project: Path) -> tuple[dict, Path]:
    sender = project.parent / "desktop-bin/osascript"
    log = project.parent / "desktop-notifications.jsonl"
    executable(
        sender,
        'import json, os, sys\nfrom pathlib import Path\nwith Path(os.environ["TEST_NOTIFICATION"]).open("a") as stream: stream.write(json.dumps(sys.argv[1:]) + "\\n")\n',
    )
    return {
        "PATH": f"{sender.parent}{os.pathsep}{os.environ['PATH']}",
        "TEST_NOTIFICATION": str(log),
        "WORKFLOW_NOTIFY": "true",
        "WORKFLOW_HOST": "claude",
        "WORKFLOW_HOST_WORKER": "0",
        "RELAY_MODE": "0",
    }, log


@pytest.mark.parametrize(
    "kind",
    [
        "permission_prompt",
        "idle_prompt",
        "elicitation_dialog",
        "elicitation_url_dialog",
    ],
)
def test_only_native_idle_or_user_input_events_notify(
    project: Path, desktop, kind: str
):
    environment, log = desktop
    results = invoke_event(
        project,
        "Notification",
        {"notification_type": kind, "message": 'Current "request"'},
        **environment,
    )
    assert len(results) == 1 and results[0].returncode == 0
    alerts = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(alerts) == 1
    assert alerts[0][-1] == 'Current "request"'
    assert alerts[0][-2] == (
        "Claude: ready for you" if kind == "idle_prompt" else "Claude: input needed"
    )


@pytest.mark.parametrize(
    "event,payload",
    [
        ("Stop", {"stop_hook_active": False}),
        ("Stop", {"stop_hook_active": True}),
        ("Stop", {"background_tasks": [{"status": "running"}]}),
        ("Stop", {"session_crons": [{"id": "continuation"}]}),
        ("Notification", {"notification_type": "auth_success"}),
        ("Notification", {"notification_type": "quota_auto_resume_started"}),
        ("Notification", {}),
    ],
)
def test_turn_stops_and_automatic_events_never_notify(
    project: Path, desktop, event: str, payload: dict
):
    environment, log = desktop
    result = invoke(
        project,
        "workflow-events.py",
        {
            "hook_event_name": event,
            "last_assistant_message": "Intermediate response",
            **payload,
        },
        **environment,
    )
    assert result.returncode == 0 and result.stdout == ""
    assert not log.exists()


@pytest.mark.parametrize("error", ["rate_limit", "overloaded", "authentication_failed"])
def test_api_failure_logging_does_not_generate_desktop_alerts(
    project: Path, desktop, error: str
):
    environment, log = desktop
    for _ in range(2):
        result = invoke(
            project, "stop-failure-logger.sh", {"error": error}, **environment
        )
        assert result.returncode == 0
    entries = (project / ".claude/logs/stop-failures.jsonl").read_text().splitlines()
    assert len(entries) == 2
    assert all(json.loads(line)["error"] == error for line in entries)
    assert not log.exists()


@pytest.mark.parametrize("invalid_graph", [False, True])
def test_output_validation_ignores_document_rules_but_checks_task_graphs(
    project: Path, invalid_graph: bool
) -> None:
    output = project / ".claude/plan.md"
    output.parent.mkdir(parents=True)
    # A legacy task index needs no document headings. The same parser is used
    # by the scheduler, and a missing dependency still makes the graph invalid.
    output.write_text(
        "- [ ] **Task 1: Ship the fix**"
        + (" — Priority: HIGH, Deps: Task 2" if invalid_graph else "")
        + "\n"
    )
    expectations = project / ".claude/expected-output.json"
    expectations.write_text(
        json.dumps(
            {
                "source": "relay-plan",
                "rules": [
                    {"type": "file_exists", "path": "missing-document.md"},
                    {
                        "type": "file_contains",
                        "path": ".claude/plan.md",
                        "sections": ["## Missing"],
                    },
                    {
                        "type": "dir_files_contain",
                        "path": "missing-specs",
                        "sections": ["## Acceptance Criteria"],
                    },
                    {
                        "type": "file_min_lines",
                        "path": ".claude/plan.md",
                        "min_lines": 100,
                    },
                    {"type": "task_index_format", "path": ".claude/plan.md"},
                ],
            }
        )
    )

    result = invoke(project, "validate-output.py", {})

    assert result.returncode == 0, result.stderr
    if invalid_graph:
        assert json.loads(result.stdout)["decision"] == "block"
        assert "unknown dependency" in result.stdout
        assert expectations.exists()
    else:
        assert result.stdout == ""
        assert not expectations.exists()


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


def test_global_edit_hooks_do_not_run_post_tool_checks(project: Path) -> None:
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
    assert all(result.returncode == 0 and result.stdout == "" for result in results)


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


@pytest.fixture
def native_worktree(project: Path) -> Path:
    setup_source(project, "python")
    worktree = project / ".claude/worktrees/native worktree's files"
    worktree.parent.mkdir(parents=True)
    git(project, "worktree", "add", "--quiet", "-b", "native", str(worktree))
    (worktree / "nested").mkdir()
    return worktree


def test_stop_verifies_the_native_worktree_instead_of_the_launch_checkout(
    project: Path, native_worktree: Path
) -> None:
    (project / ".claude/project-commands.json").write_text(
        json.dumps({"lint": None, "test": "python3 -c 'raise SystemExit(0)'"})
    )
    (native_worktree / ".claude/project-commands.json").write_text(
        json.dumps(
            {
                "lint": None,
                "test": "python3 -c 'import sys; print(\"native checkout failed\"); sys.exit(1)'",
            }
        )
    )
    result = invoke(
        project,
        "lint-on-stop.sh",
        {"cwd": str(native_worktree / "nested"), "session_id": "native"},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "block"
    assert "native checkout failed" in json.loads(result.stdout)["reason"]
    record = json.loads(
        next((native_worktree / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == "failed"
    assert not (project / ".claude/verification").exists()


def test_task_graph_validation_follows_the_active_native_checkout(
    project: Path, native_worktree: Path
) -> None:
    expectations = native_worktree / ".claude/expected-output.json"
    expectations.write_text(
        json.dumps(
            {
                "source": "native test",
                "rules": [{"type": "task_index_format", "path": "plan.md"}],
            }
        )
    )
    (project / "plan.md").write_text("- [ ] **Task 1: Old checkout**\n")
    payload = {"cwd": str(native_worktree / "nested"), "session_id": "native"}
    result = invoke(project, "validate-output.py", payload)
    assert json.loads(result.stdout)["decision"] == "block"
    assert expectations.exists()
    (native_worktree / "plan.md").write_text("- [ ] **Task 1: Actual checkout**\n")
    result = invoke(project, "validate-output.py", payload)
    assert result.returncode == 0 and result.stdout == "", result.stderr
    assert not expectations.exists()


@pytest.mark.parametrize("hook", ["lint-on-stop.sh", "validate-output.py"])
def test_missing_active_checkout_cannot_fall_back_to_success(
    project: Path, hook: str
) -> None:
    result = invoke(project, hook, {"cwd": str(project / "missing-worktree")})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "block"


def test_native_cwd_handling_preserves_a_project_inside_a_monorepo(
    project: Path,
) -> None:
    component = project / "backend"
    (component / ".claude").mkdir(parents=True)
    (component / "src").mkdir()
    (component / ".claude/expected-output.json").write_text(
        json.dumps(
            {
                "source": "backend",
                "rules": [{"type": "task_index_format", "path": "plan.md"}],
            }
        )
    )
    result = invoke(
        project,
        "validate-output.py",
        {"cwd": str(component / "src")},
        CLAUDE_PROJECT_DIR=str(component),
    )
    assert json.loads(result.stdout)["decision"] == "block"
    (component / "plan.md").write_text("- [ ] **Task 1: Backend task**\n")
    result = invoke(
        project,
        "validate-output.py",
        {"cwd": str(component / "src")},
        CLAUDE_PROJECT_DIR=str(component),
    )
    assert result.returncode == 0 and result.stdout == "", result.stderr


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
            "notification_type": "idle_prompt",
            "message": 'Current "response"',
            "transcript_path": "missing.jsonl",
        },
        PATH=f"{tool.parent}{os.pathsep}{os.environ['PATH']}",
        TEST_NOTIFICATION=str(output),
        WORKFLOW_NOTIFY="true",
        WORKFLOW_HOST_WORKER="0",
        RELAY_MODE="0",
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
    assert result.returncode == 0, result.stderr
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    if commands is None or commands == {}:
        assert json.loads(result.stdout)["decision"] == "block"
        assert record["status"] == "incomplete"
        assert "Unconfigured" in result.stdout
    else:
        assert result.stdout == ""
        assert record["status"] == "disabled"
    formatted = subprocess.run(
        [str(ROOT / "scripts/format-project.sh"), str(project)],
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
    )
    assert formatted.returncode == 0, formatted.stderr
    assert not Path(environment["TEST_CALLS"]).exists()


@pytest.mark.parametrize(
    "markers",
    [
        ("go.mod",),
        ("go.work",),
        ("package.json", "tsconfig.json"),
        ("go.mod", "pyproject.toml", "package.json"),
        ("mix.exs", "go.mod"),
    ],
)
@pytest.mark.parametrize("failure", [False, True])
def test_stop_runs_project_checks_across_languages_and_preserves_pipe_failures(
    project: Path, markers: tuple[str, ...], failure: bool
) -> None:
    for marker in markers:
        (project / marker).touch()
    (project / "source.txt").write_text("unchanged\n")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Initial")
    (project / ".claude").mkdir(exist_ok=True)
    (project / ".claude/project-commands.json").write_text(
        json.dumps(
            {
                "lint": "printf 'static check ran\\n'",
                "test": (
                    "printf 'behavior failed\\n'; false | cat"
                    if failure
                    else "printf 'behavior checked\\n'"
                ),
                "format": "touch formatting-must-not-run",
            }
        )
    )
    result = invoke(project, "lint-on-stop.sh", {"session_id": "polyglot"})
    assert result.returncode == 0, result.stderr
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == ("failed" if failure else "passed")
    assert record["checked"] == record["after"]
    assert (project / "source.txt").read_text() == "unchanged\n"
    assert not (project / "formatting-must-not-run").exists()
    if failure:
        assert json.loads(result.stdout)["decision"] == "block"
        assert (
            "static check ran" in result.stdout and "behavior failed" in result.stdout
        )
    else:
        assert result.stdout == ""


@pytest.mark.parametrize(
    "verify, status",
    [
        (None, "disabled"),
        ("", "disabled"),
        ("printf 'product checked\\n'", "passed"),
        ("printf 'product failed\\n'; false | cat", "failed"),
        ("printf 'connection refused\\n'; exit 1", "incomplete"),
        ("workflow-product-command-not-installed", "failed"),
        ("printf changed >> source.txt", "changed"),
    ],
)
def test_stop_product_check_owns_success_failure_and_availability(
    project: Path, verify: str | None, status: str
) -> None:
    (project / "source.txt").write_text("original\n")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Baseline")
    (project / ".claude").mkdir()
    (project / ".claude/project-commands.json").write_text(
        json.dumps({"lint": None, "test": None, "verify": verify})
    )
    result = invoke(project, "lint-on-stop.sh", {"session_id": "product-check"})
    assert result.returncode == 0, result.stderr
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == status
    assert (record["checked"] == record["after"]) == (status != "changed")
    if status in ("passed", "disabled"):
        assert result.stdout == ""
    else:
        assert json.loads(result.stdout)["decision"] == "block"
        expected = (
            "Verification is incomplete" if status == "incomplete" else "project verify"
        )
        assert expected in result.stdout


@pytest.mark.parametrize("failed_action", [None, "lint", "test", "verify"])
def test_plugin_repository_stop_runs_all_required_checks(
    project: Path, failed_action: str | None
) -> None:
    # Use the plugin's actual contract so missing/ignored repository configuration
    # cannot silently leave its own Stop hook on the not_applicable path.
    (project / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    (project / ".claude").mkdir()
    (project / ".claude/project-commands.json").write_bytes(
        (ROOT / ".claude/project-commands.json").read_bytes()
    )
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Plugin development contract")
    make = project.parent / "bin/make"
    calls = project.parent / "make-calls.jsonl"
    executable(
        make,
        """import json, os, sys
with open(os.environ["TEST_CALLS"], "a") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
print("project " + sys.argv[1])
sys.exit(int(sys.argv[1] == os.environ["TEST_FAILED_ACTION"]))
""",
    )
    result = invoke(
        project,
        "lint-on-stop.sh",
        {"session_id": "plugin-development"},
        PATH=f"{make.parent}{os.pathsep}{os.environ['PATH']}",
        TEST_CALLS=str(calls),
        TEST_FAILED_ACTION=failed_action or "",
    )
    assert result.returncode == 0, result.stderr
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        ["lint"],
        ["test"],
        ["verify"],
    ]
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["checked"] == record["after"]
    assert record["status"] == ("failed" if failed_action else "passed")
    if failed_action:
        assert json.loads(result.stdout)["decision"] == "block"
        assert f"project {failed_action}" in json.loads(result.stdout)["reason"]
    else:
        assert result.stdout == ""


@pytest.mark.parametrize("marker", ["go.mod", "package.json", "pyproject.toml"])
def test_missing_checks_cannot_be_recorded_as_verified(
    project: Path, marker: str
) -> None:
    (project / marker).touch()
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Initial")
    (project / ".claude").mkdir(exist_ok=True)
    (project / ".claude/project-commands.json").write_text(
        json.dumps(
            {
                "test": "printf 'configured test ran\\n'",
            }
        )
    )
    for attempt in range(4):
        result = invoke(
            project,
            "lint-on-stop.sh",
            {"session_id": "missing", "stop_hook_active": attempt > 0},
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        if attempt < 3:
            assert report["decision"] == "block"
            assert "Unconfigured" in report["reason"] and "lint" in report["reason"]
        else:
            assert report["continue"] is False
    record = json.loads(
        next((project / ".claude/verification").glob("*.json")).read_text()
    )
    assert record["status"] == "blocked"


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
