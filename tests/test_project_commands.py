"""Behavioral checks for structured command detection and verification gates."""

import json
import os
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PRIMITIVES = PLUGIN_ROOT / "scripts/lib/parallel-primitives.sh"
GENERATOR = PLUGIN_ROOT / "scripts/configure-project.sh"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project with spaces"
    (project_dir / ".claude").mkdir(parents=True)
    return project_dir


def configure(project: Path, commands: object) -> None:
    (project / ".claude/project-commands.json").write_text(json.dumps(commands))


def readiness(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(PLUGIN_ROOT / "scripts/project-commands.py"),
            "readiness",
            str(project),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "marker",
    [
        "go.mod",
        "go.work",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "tsconfig.json",
    ],
)
def test_readiness_reports_missing_checks_without_selecting_tools(
    project: Path, marker: str
) -> None:
    (project / marker).touch()
    result = readiness(project)
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "unconfigured"
    assert report["verification"] == "not_run"
    assert all(check["status"] == "unconfigured" for check in report["checks"].values())
    assert not (project / ".claude/project-commands.json").exists()


def test_readiness_reports_mixed_projects_and_does_not_execute_commands(
    project: Path,
) -> None:
    for marker in ("go.mod", "pyproject.toml", "tsconfig.json"):
        (project / marker).touch()
    configure(project, {"lint": "touch must-not-exist", "test": "exit 9"})
    result = readiness(project)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "configured"
    assert report["languages"] == ["go", "python", "typescript"]
    assert report["verification"] == "not_run"
    assert report["checks"]["lint"]["command"] == "touch must-not-exist"
    assert not (project / "must-not-exist").exists()


@pytest.mark.parametrize(
    "commands, status, code",
    [
        ({"lint": None, "test": ""}, "disabled", 0),
        ({"lint": None, "test": "true"}, "configured", 0),
        ({"test": "true"}, "unconfigured", 1),
        ({}, "unconfigured", 1),
    ],
)
def test_readiness_distinguishes_missing_and_disabled_checks(
    project: Path, commands: dict, status: str, code: int
) -> None:
    configure(project, commands)
    result = readiness(project)
    assert result.returncode == code, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == status
    assert report["verification"] == "not_run"


def test_readiness_handles_invalid_configuration_as_json(project: Path) -> None:
    configure(project, {"test": ["not a command"]})
    result = readiness(project)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "invalid"
    assert "test must be a string or null" in report["error"]


def test_readiness_keeps_legacy_elixir_visible_and_skips_unknown_projects(
    project: Path,
) -> None:
    assert json.loads(readiness(project).stdout)["status"] == "not_applicable"
    (project / "mix.exs").touch()
    assert json.loads(readiness(project).stdout)["status"] == "legacy_elixir"
    # Mixed projects must choose aggregate commands instead of checking just Elixir.
    (project / "go.mod").touch()
    assert json.loads(readiness(project).stdout)["status"] == "unconfigured"


@pytest.mark.parametrize(
    "marker", ["go.mod", "go.work", "package.json", "requirements.txt"]
)
@pytest.mark.parametrize("action", ["test", "lint"])
def test_executor_requires_selected_checks_for_supported_stacks(
    project: Path, marker: str, action: str
) -> None:
    (project / marker).write_text(
        '{"scripts": {"test": "some-test"}}' if marker == "package.json" else ""
    )
    result = shell(project, f'detect_{action}_command "$2"')
    assert result.returncode != 0
    assert "unconfigured" in result.stderr


@pytest.mark.parametrize(
    "markers",
    [
        ("go.mod",),
        ("go.work",),
        ("package.json",),
        ("mix.exs", "go.mod"),
        ("mix.exs", "package.json"),
        ("pyproject.toml", "go.mod"),
    ],
)
def test_generator_preserves_unknown_and_selected_go_node_commands(
    project: Path, markers: tuple[str, ...]
) -> None:
    for marker in markers:
        (project / marker).write_text(
            '{"scripts": {"test": "vitest"}}' if marker == "package.json" else ""
        )
    assert generate(project).returncode == 0
    commands = json.loads((project / ".claude/project-commands.json").read_text())
    assert "test" not in commands and "lint" not in commands
    assert (
        shell(project, 'run_verification_gate "$2" "$2/verification"').returncode != 0
    )
    selected = {"lint": "make check-static", "test": "make check-behavior"}
    configure(project, selected)
    assert generate(project).returncode == 0
    assert (
        json.loads((project / ".claude/project-commands.json").read_text()) == selected
    )


@pytest.mark.parametrize("action", ["test", "lint"])
def test_verification_gate_does_not_hide_pipeline_failure(
    project: Path, action: str
) -> None:
    configure(project, {"test": "true", "lint": "true", action: "false | cat"})
    result = shell(project, 'run_verification_gate "$2" "$2/verification"')
    assert result.returncode != 0


def shell(
    project: Path, script: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail\nsource "$1"\n' + script,
            "test",
            str(PRIMITIVES),
            str(project),
            *arguments,
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )


def generate(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GENERATOR)],
        cwd=project,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_test_gate_runs_test_instead_of_next_markdown_row(project: Path) -> None:
    (project / ".claude/AGENTS.md").write_text(
        "| Test | `false` |\n| Lint | `false` |\n| Format | `false` |\n"
    )
    configure(
        project, {"test": "printf '%s' 'tests ran' > 'test result'", "lint": "false"}
    )

    result = shell(project, 'run_test_gate "$2" "$2/gate.log"')

    assert result.returncode == 0, result.stderr
    assert (project / "test result").read_text() == "tests ran"
    lint = shell(project, 'detect_lint_command "$2"')
    assert lint.returncode == 0, lint.stderr
    assert lint.stdout == "false\n"


def test_commands_preserve_quotes_pipes_backslashes_and_multiline_shell(
    project: Path,
) -> None:
    command = (
        "printf '%s\\n' 'two  spaces' 'a|b' \"quoted\" | cat\nprintf '%s' '`literal`'"
    )
    configure(project, {"test": command, "lint": command})
    for action in ("test", "lint"):
        result = shell(project, f'detect_{action}_command "$2"')
        assert result.returncode == 0, result.stderr
        assert result.stdout == command + "\n"

    gate = shell(project, 'run_test_gate "$2" "$2/gate.log"')
    assert gate.returncode == 0, gate.stderr
    assert (project / "gate.log").read_text() == "two  spaces\na|b\nquoted\n`literal`"


@pytest.mark.parametrize("commands", [None, {}, {"build": "custom build"}])
def test_only_missing_elixir_configuration_falls_back_without_parsing_markdown(
    project: Path, commands: object
) -> None:
    (project / "mix.exs").touch()
    (project / ".claude/AGENTS.md").write_text(
        "| Test | `false` |\n| Lint | `false` |\n"
    )
    if commands is not None:
        configure(project, commands)

    result = shell(project, 'detect_test_command "$2"\ndetect_lint_command "$2"')

    if commands is None:
        assert result.returncode == 0, result.stderr
        assert result.stdout == "mix test\nmix credo\n"
    else:
        assert result.returncode != 0
        assert "unconfigured" in result.stderr
        assert result.stdout == ""


@pytest.mark.parametrize("disabled", [None, ""])
def test_disabled_commands_do_not_fall_back(
    project: Path, disabled: str | None
) -> None:
    (project / "mix.exs").touch()
    configure(project, {"test": disabled, "lint": disabled})

    result = shell(
        project,
        'detect_test_command "$2"\ndetect_lint_command "$2"\nrun_test_gate "$2"',
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("\n\n")
    assert "skipping test gate" in result.stdout


@pytest.mark.parametrize(
    "contents",
    ["{", "[]", '{"test": false}', '{"lint": ["ruff"]}', '{"tset": "false"}'],
)
def test_invalid_config_fails_verification_even_in_a_conditional(
    project: Path, contents: str
) -> None:
    (project / "mix.exs").touch()
    (project / ".claude/project-commands.json").write_text(contents)

    result = shell(
        project, 'if run_test_gate "$2" "$2/gate.log"; then exit 0; else exit 7; fi'
    )

    assert result.returncode == 7
    assert "project-commands.json" in result.stderr
    assert "skipping" not in result.stdout


def test_failing_test_command_fails_gate(project: Path) -> None:
    configure(project, {"test": "printf '%s' 'test failure'; exit 3", "lint": "true"})

    result = shell(
        project, 'if run_test_gate "$2" "$2/gate.log"; then exit 0; else exit 7; fi'
    )

    assert result.returncode == 7
    assert (project / "gate.log").read_text() == "test failure"


def test_generator_creates_config_and_guide_with_matching_commands(
    project: Path,
) -> None:
    (project / "mix.exs").touch()

    result = generate(project)

    assert result.returncode == 0, result.stderr
    commands = json.loads((project / ".claude/project-commands.json").read_text())
    assert commands == {
        "build": "mix compile",
        "test": "mix test",
        "lint": "mix credo",
        "format": "mix format",
        "run": None,
    }
    guide = (project / ".claude/AGENTS.md").read_text()
    assert "| Test    | `mix test` |" in guide
    assert "| Lint    | `mix credo` |" in guide
    detected = shell(project, 'detect_test_command "$2"\ndetect_lint_command "$2"')
    assert detected.stdout == "mix test\nmix credo\n"


def test_generator_preserves_overrides_and_disabled_actions_on_refresh(
    project: Path,
) -> None:
    (project / "mix.exs").touch()
    command = "custom-test --label 'two  spaces' | cat"
    configure(project, {"test": command, "lint": None})

    for _ in range(2):
        result = generate(project)
        assert result.returncode == 0, result.stderr

    commands = json.loads((project / ".claude/project-commands.json").read_text())
    assert commands["test"] == command
    assert commands["lint"] is None
    assert commands["build"] == "mix compile"
    guide = (project / ".claude/AGENTS.md").read_text()
    assert f"| Test    | `{command}` |" in guide
    assert "| Lint    | `N/A` |" in guide


def test_generator_leaves_invalid_config_and_existing_guide_intact(
    project: Path,
) -> None:
    (project / ".claude/project-commands.json").write_text("invalid")
    (project / ".claude/AGENTS.md").write_text("existing guide")

    result = generate(project)

    assert result.returncode != 0
    assert "project-commands.json" in result.stderr
    assert (project / ".claude/project-commands.json").read_text() == "invalid"
    assert (project / ".claude/AGENTS.md").read_text() == "existing guide"


def test_python_detection_does_not_invent_a_toolchain(project: Path) -> None:
    (project / "pyproject.toml").write_text("[tool.black]\n[tool.mypy]\n")
    for action in ("test", "lint"):
        detected = shell(project, f'detect_{action}_command "$2"')
        assert detected.returncode != 0
        assert "unconfigured" in detected.stderr
        assert detected.stdout == ""
    result = generate(project)
    assert result.returncode == 0, result.stderr
    commands = json.loads((project / ".claude/project-commands.json").read_text())
    assert all(action not in commands for action in ("build", "test", "lint", "format"))
    gated = shell(project, 'run_verification_gate "$2" "$2/verification"')
    assert gated.returncode != 0


def test_python_explicit_disables_are_preserved_and_respected(project: Path) -> None:
    (project / "pyproject.toml").touch()
    configure(project, {"test": None, "lint": None})
    result = generate(project)
    assert result.returncode == 0, result.stderr
    gated = shell(project, 'run_verification_gate "$2" "$2/verification"')
    assert gated.returncode == 0, gated.stderr


def test_python_generator_preserves_the_project_stack(project: Path) -> None:
    (project / "pyproject.toml").write_text("[tool.black]\n[tool.mypy]\n")
    selected = {
        "test": "poetry run pytest",
        "lint": "poetry run mypy .",
        "format": "poetry run black .",
    }
    configure(project, selected)
    result = generate(project)
    assert result.returncode == 0, result.stderr
    commands = json.loads((project / ".claude/project-commands.json").read_text())
    assert all(commands[action] == value for action, value in selected.items())


def test_worker_worktree_inherits_untracked_command_overrides(
    project: Path, tmp_path: Path
) -> None:
    for arguments in (
        ["init", "--quiet"],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "initial",
        ],
    ):
        subprocess.run(
            ["git", "-C", str(project), *arguments], check=True, capture_output=True
        )
    configure(project, {"test": "printf '%s' 'worker tests'", "lint": None})
    (project / ".claude/AGENTS.md").write_text("project guidance")
    worktree = tmp_path / "worker worktree"

    result = shell(
        project,
        'create_worker_worktree "$2" "$3" worker\ndetect_test_command "$3"',
        str(worktree),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith("printf '%s' 'worker tests'\n")
    assert (worktree / ".claude/project-commands.json").read_bytes() == (
        project / ".claude/project-commands.json"
    ).read_bytes()
    assert (worktree / ".claude/AGENTS.md").read_text() == "project guidance"
