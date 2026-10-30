"""Exercise repository tasks through the real Maak CLI, without running nested checks."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    project = tmp_path / "project with spaces"
    project.mkdir()
    shutil.copyfile(ROOT / "maak.scm", project / "maak.scm")
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch(mode=0o755)
    uv = project / "uv with spaces"
    uv.write_text(
        '#!/usr/bin/env python3\n'
        'import json, os, sys\n'
        'with open(os.environ["UV_CALLS"], "a") as output:\n'
        '    output.write(json.dumps({"args": sys.argv[1:], "pi": os.getenv("WORKFLOW_REQUIRE_PI"), "autolith": os.getenv("WORKFLOW_REQUIRE_AUTOLITH")}) + "\\n")\n'
        'if os.getenv("FAIL_WHEN") and os.environ["FAIL_WHEN"] in " ".join(sys.argv[1:]):\n'
        '    sys.exit(17)\n'
    )
    uv.chmod(0o755)
    calls = project / "uv-calls.jsonl"
    environment = {
        **os.environ,
        "UV": str(uv),
        "UV_CALLS": str(calls),
        "GUILE_AUTO_COMPILE": "0",
        "MAAK_NO_BANNER": "1",
    }
    environment.pop("FAIL_WHEN", None)
    return project, environment, calls


def maak(project, *arguments: str) -> subprocess.CompletedProcess[str]:
    directory, environment, _ = project
    executable = shutil.which("maak")
    assert executable, "Install the pinned Maak and add its bin directory to PATH."
    return subprocess.run(
        [executable, "--no-env-file", *arguments],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


def invocations(project) -> list[dict]:
    return [json.loads(line) for line in project[2].read_text().splitlines()]


def test_setup_only_synchronizes_the_locked_environment(project):
    result = maak(project, "setup")
    assert result.returncode == 0, result.stderr
    assert [call["args"] for call in invocations(project)] == [
        ["sync", "--locked", "--dev"]
    ]


@pytest.mark.parametrize("task", [(), ("check",)])
def test_default_and_check_run_all_gates_in_order_without_installing(project, task):
    result = maak(project, *task)
    assert result.returncode == 0, result.stderr
    calls = [call["args"] for call in invocations(project)]
    preflight = [call for call in calls if call[0] == "sync"]
    assert preflight
    assert all("--check" in call and "--offline" in call for call in preflight)
    checks = [call for call in calls if call[0] == "run"]
    assert all(call[:4] == ["run", "--frozen", "--no-sync", "--offline"] for call in checks)
    assert [call[4:] for call in checks] == [
        ["python", "-m", "ruff", "check", "--no-fix", "."],
        ["bash", "scripts/validate-hooks.sh"],
        ["python", "scripts/sync-hosts.py", "--check"],
        ["python", "-m", "pytest", "-q"],
        ["python", "tests/smoke_delivery.py"],
    ]


@pytest.mark.parametrize("task", ["lint", "test", "verify", "sync-hosts", "check-hosts"])
def test_checks_reject_a_missing_environment_before_invoking_uv(project, task):
    (project[0] / ".venv/bin/python").unlink()
    result = maak(project, task)
    assert result.returncode != 0
    assert "Run maak setup" in result.stderr
    assert not project[2].exists()


@pytest.mark.parametrize(
    "failure, forbidden",
    [
        ("sync", ["ruff", "pytest", "smoke_delivery.py"]),
        ("ruff", ["validate-hooks.sh", "pytest", "smoke_delivery.py"]),
        ("pytest", ["smoke_delivery.py"]),
        ("smoke_delivery.py", []),
    ],
)
def test_check_stops_and_fails_when_a_gate_fails(project, failure, forbidden):
    project[1]["FAIL_WHEN"] = failure
    result = maak(project, "check")
    assert result.returncode != 0
    calls = json.dumps(invocations(project))
    assert failure in calls
    assert all(later not in calls for later in forbidden)
    if failure == "sync":
        assert "Run maak setup" in result.stderr
        assert "uv lock" in result.stderr


def test_dry_run_works_without_setup_and_does_not_execute_commands(project):
    (project[0] / ".venv/bin/python").unlink()
    result = maak(project, "--dry-run", "check")
    assert result.returncode == 0, result.stderr
    assert "--offline" in result.stdout
    assert "smoke_delivery.py" in result.stdout
    assert not project[2].exists()


def test_native_host_checks_require_both_hosts(project):
    result = maak(project, "check-hosts")
    assert result.returncode == 0, result.stderr
    calls = invocations(project)
    host_tests = next(call for call in calls if "pytest" in call["args"])
    assert host_tests["pi"] == host_tests["autolith"] == "1"
    assert calls[-2]["args"][-1] == "tests/smoke_autolith.py"
    assert calls[-1]["args"][-1] == "tests/smoke_host_runners.py"
