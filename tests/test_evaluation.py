"""Evaluation failures never become acceptance in any Ralph mode."""

import copy
import json
import os
from pathlib import Path
import subprocess

import pytest

from test_ralph_pipeline import EVALUATION, git

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project = tmp_path / "project with 'quotes' and spaces"
    project.mkdir()
    (project / ".gitignore").write_text(".claude/\n")
    (project / "source.py").write_text("original\n")
    git(project, "init", "--quiet", "-b", "main")
    git(project, "config", "user.name", "Test")
    git(project, "config", "user.email", "test@example.com")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Initial")
    tool = tmp_path / "bin/claude"
    tool.parent.mkdir()
    tool.write_text(
        """#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
sys.stdin.read()
directory = pathlib.Path('.claude')
directory.mkdir(exist_ok=True)
(directory / 'argv.json').write_text(json.dumps(sys.argv[1:]))
print('evaluator diagnostic', file=sys.stderr, flush=True)
mode = os.environ.get('TEST_EVAL_MODE', '')
if mode == 'timeout':
    time.sleep(30)
if mode in ('dirty', 'commit'):
    pathlib.Path('source.py').write_text('changed by an outside writer')
    if mode == 'commit':
        subprocess.run(['git', 'add', 'source.py'], check=True)
        subprocess.run(['git', 'commit', '--quiet', '-m', 'Changed candidate'], check=True)
if mode == 'guidance':
    (directory / 'project-commands.json').write_text('{"test":"false"}')
if mode == 'spec':
    (directory / 'specs').mkdir(exist_ok=True)
    (directory / 'specs/requirements.md').write_text('Changed criteria')
if mode == 'ui_change':
    pathlib.Path(os.environ['RALPH_EVAL_UI_EVIDENCE'], 'interaction.txt').write_text('Changed evidence')
if mode == 'malformed':
    print('{invalid')
elif mode != 'missing':
    print(json.dumps({'subtype': 'success', 'is_error': mode == 'api_error',
                      'structured_output': json.loads(os.environ['TEST_EVAL_PAYLOAD'])}))
sys.exit(int(os.environ.get('TEST_EVAL_EXIT', '0')))
"""
    )
    tool.chmod(0o755)
    return project


def evaluate(
    project: Path, payload=None, *, mode="", exit_code=0, variables=None, base=None
):
    revision = git(project, "rev-parse", "HEAD")
    artifacts = project / ".claude/evaluation"
    artifacts.mkdir(parents=True, exist_ok=True)
    # An earlier ACCEPT must be replaced even if this invocation fails.
    (artifacts / "verdict.json").write_text('{"verdict":"ACCEPT"}')
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/evaluate.py"),
            "--base",
            base or revision,
            "--revision",
            revision,
            "--verdict",
            str(artifacts / "verdict.json"),
            "--summary",
            str(artifacts / "summary.md"),
            "--log",
            str(artifacts / "cli.json"),
            "--timeout",
            "0.2" if mode == "timeout" else "5",
        ],
        cwd=project,
        input="Evaluate the fixture requirement",
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "TEST_EVAL_PAYLOAD": json.dumps(EVALUATION if payload is None else payload),
            "TEST_EVAL_MODE": mode,
            "TEST_EVAL_EXIT": str(exit_code),
            "RALPH_EVALUATE_UI": "false",
            **(variables or {}),
        },
        timeout=8,
    )
    return result, json.loads((artifacts / "verdict.json").read_text())


def test_valid_evaluation_binds_evidence_and_uses_read_only_permissions(project: Path):
    result, verdict = evaluate(project)
    assert result.returncode == 0, result.stderr
    assert verdict["verdict"] == "ACCEPT"
    assert verdict["revision"] == git(project, "rev-parse", "HEAD")
    assert verdict["checked"]["revision"] == verdict["revision"]
    arguments = json.loads((project / ".claude/argv.json").read_text())
    assert "--dangerously-skip-permissions" not in arguments
    assert "--restricted" in arguments
    assert arguments[arguments.index("--tools") + 1] == "Read,Glob,Grep"
    assert arguments[arguments.index("--permission-mode") + 1] == "dontAsk"
    assert "mcp__*" in arguments
    assert "--strict-mcp-config" in arguments
    settings = json.loads(arguments[arguments.index("--settings") + 1])
    assert "Read(.env)" in settings["permissions"]["deny"]
    assert (
        project / ".claude/evaluation/cli.json.stderr.log"
    ).read_text().strip() == "evaluator diagnostic"
    assert "Full run report" in (project / ".claude/evaluation/summary.md").read_text()


@pytest.mark.parametrize(
    "mode",
    [
        "missing",
        "malformed",
        "api_error",
        "timeout",
        "dirty",
        "commit",
        "guidance",
        "spec",
    ],
)
def test_process_and_revision_errors_are_explicit(project: Path, mode: str):
    result, verdict = evaluate(project, mode=mode)
    assert result.returncode == 3
    assert result.stdout.strip() == "ERROR"
    assert verdict["verdict"] == "ERROR"
    assert verdict["reason"]


def test_nonzero_exit_cannot_accept_a_valid_result(project: Path):
    result, verdict = evaluate(project, exit_code=7)
    assert result.returncode == 3
    assert verdict["verdict"] == "ERROR"
    assert "exited 7" in verdict["reason"]


@pytest.mark.parametrize(
    "defect",
    [
        "missing_scores",
        "missing_criteria",
        "empty_notes",
        "bad_average",
        "out_of_range",
        "boolean_score",
        "nan",
        "low_score",
        "critical_issue",
        "unknown_verdict",
        "missing_integrity",
        "empty_integrity_evidence",
        "failed_integrity",
        "failed_criterion",
        "partial_criterion",
    ],
)
def test_invalid_or_contradictory_evidence_is_an_error(project: Path, defect: str):
    payload = copy.deepcopy(EVALUATION)
    if defect == "missing_scores":
        del payload["scores"]
    elif defect == "missing_criteria":
        payload["criteria_results"] = []
    elif defect == "empty_notes":
        payload["criteria_results"][0]["notes"] = "  "
    elif defect == "bad_average":
        payload["average"] = 5
    elif defect == "out_of_range":
        payload["average"] = 8
    elif defect == "boolean_score":
        payload["scores"]["correctness"] = True
    elif defect == "nan":
        payload["average"] = float("nan")
    elif defect == "low_score":
        payload["scores"] = {name: 2 for name in payload["scores"]}
        payload["average"] = 2
    elif defect == "critical_issue":
        payload["issues"] = [
            {
                "dimension": "correctness",
                "severity": "critical",
                "file": "source.py",
                "line": 1,
                "description": "Broken requirement",
            }
        ]
    elif defect == "missing_integrity":
        del payload["verification_integrity"]
    elif defect == "empty_integrity_evidence":
        payload["verification_integrity"]["notes"] = " "
    elif defect == "failed_integrity":
        payload["verification_integrity"]["status"] = "FAIL"
    elif defect == "failed_criterion":
        payload["criteria_results"][0]["result"] = "FAIL"
    elif defect == "partial_criterion":
        payload["criteria_results"][0]["result"] = "PARTIAL"
    else:
        payload["verdict"] = "UNKNOWN"
    result, verdict = evaluate(project, payload)
    assert result.returncode == 3
    assert verdict["verdict"] == "ERROR"


def test_valid_revise_is_distinct_from_error(project: Path):
    payload = {
        **copy.deepcopy(EVALUATION),
        "verdict": "REVISE",
        "revise_guidance": "Fix the requirement",
    }
    result, verdict = evaluate(project, payload)
    assert result.returncode == 1
    assert verdict["verdict"] == "REVISE"


@pytest.mark.parametrize("evidence", ["missing", "present", "changed", "outside"])
def test_ui_evaluation_requires_current_local_evidence(project: Path, evidence: str):
    directory = project / ".claude/ui"
    if evidence == "outside":
        directory = project.parent / "outside-ui"
    if evidence != "missing":
        directory.mkdir(parents=True)
        (directory / "interaction.txt").write_text("Recorded interaction")
    result, verdict = evaluate(
        project,
        mode="ui_change" if evidence == "changed" else "",
        variables={
            "RALPH_EVALUATE_UI": "true",
            "RALPH_EVAL_UI_EVIDENCE": str(directory),
        },
    )
    if evidence == "present":
        assert result.returncode == 0, result.stderr
        assert len(verdict["ui_evidence_sha256"]) == 64
    else:
        assert result.returncode == 3
        assert verdict["verdict"] == "ERROR"


def test_protected_changes_do_not_leak_through_controller_diff(project: Path):
    base = git(project, "rev-parse", "HEAD")
    (project / ".env").write_text("EXAMPLE=private-fixture-value\n")
    git(project, "add", ".env")
    git(project, "commit", "--quiet", "-m", "Protected change")
    result, verdict = evaluate(project, base=base)
    assert result.returncode == 3
    assert "protected secret paths" in verdict["reason"]
    assert not (project / ".claude/argv.json").exists()
    assert not (project / ".claude/evaluation/cli.json.diff").exists()


def test_intermediate_secret_changes_are_not_exposed_in_history(project: Path):
    base = git(project, "rev-parse", "HEAD")
    secret = project / ".env"
    secret.write_text("EXAMPLE=private-fixture-value\n")
    git(project, "add", ".env")
    git(project, "commit", "--quiet", "-m", "Intermediate protected change")
    secret.unlink()
    git(project, "add", ".env")
    git(project, "commit", "--quiet", "-m", "Remove intermediate protected change")
    result, verdict = evaluate(project, base=base)
    assert result.returncode == 3
    assert "protected secret paths" in verdict["reason"]
    assert not (project / ".claude/evaluation/cli.json.history").exists()


@pytest.mark.parametrize("mode", ["", "missing"])
def test_direct_evaluate_mode_uses_the_same_read_only_contract(
    project: Path, mode: str
):
    spec = project / ".claude/specs/direct"
    spec.mkdir(parents=True)
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "skills/ralph/scripts/loop.sh"),
            str(spec),
            "evaluate",
            "1",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(project),
            "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "TEST_EVAL_PAYLOAD": json.dumps(EVALUATION),
            "TEST_EVAL_MODE": mode,
            "RALPH_EVALUATE_UI": "false",
        },
        timeout=8,
    )
    assert result.returncode == (0 if not mode else 3), result.stdout + result.stderr
    arguments = json.loads((project / ".claude/argv.json").read_text())
    assert "--dangerously-skip-permissions" not in arguments
    assert arguments[arguments.index("--tools") + 1] == "Read,Glob,Grep"
    path = next((project / ".claude/ralph/direct/runs").glob("*/eval-verdict.json"))
    assert json.loads(path.read_text())["verdict"] == (
        "ACCEPT" if not mode else "ERROR"
    )
