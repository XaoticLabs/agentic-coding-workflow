"""Improvement notebooks preserve resumable work without running experiments."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "skills/improve-workflow/scripts/notebook.py"


@pytest.fixture
def project(tmp_path):
    project = tmp_path / "project with 'quotes' and spaces"
    project.mkdir()
    (project / ".gitignore").write_text(".claude/\n")
    (project / "source.txt").write_text("original\n")
    for arguments in (
        ["init", "--quiet"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--quiet",
            "-m",
            "initial",
        ],
    ):
        subprocess.run(["git", *arguments], cwd=project, check=True)
    return project


def call(project, action, *arguments):
    return subprocess.run(
        [
            sys.executable,
            str(NOTEBOOK),
            action,
            *arguments,
            "--project-dir",
            str(project),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )


def start(project, name="context-loading"):
    result = call(project, "start", name, "--idea", "Reduce context loaded by prime")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    record = Path(summary["record"])
    return record, json.loads(record.read_text())


def test_start_captures_dirty_source_and_status_is_read_only(project):
    (project / "source.txt").write_text("local work\n")
    nested = project / "nested"
    nested.mkdir()
    record, state = start(nested)
    assert record == project / ".claude/improvements/context-loading/experiment.json"
    assert state["starting_source"]["scope"] == "worktree"
    assert state["baseline"]["source"] == state["starting_source"]
    assert state["plan"]["authorized_budget_usd"] is None
    assert state["evidence"] == state["decisions"] == []
    assert "NOT_RUN" in record.with_name("report.md").read_text()
    before = {path: path.read_bytes() for path in record.parent.iterdir()}
    result = call(project, "status", "context-loading")
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)["experiments"][0]
    assert status["stage"] == "prepare" and status["next_action"]
    assert before == {path: path.read_bytes() for path in record.parent.iterdir()}
    assert (project / "source.txt").read_text() == "local work\n"


def test_restart_resumes_existing_record_without_overwriting_history(project):
    record, state = start(project)
    state.update(stage="compare", next_action="Rerun the failing product check.")
    state["evidence"].append(
        {"arm": "candidate", "outcome": "failed", "report": "failure.log"}
    )
    state["decisions"].append({"outcome": "revise", "reason": "Product check failed."})
    record.write_text(json.dumps(state))
    report = record.with_name("report.md")
    report.write_text("Retained failed trial and next action.\n")
    result = call(project, "start", "context-loading", "--idea", "A different idea")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["created"] is False
    assert json.loads(record.read_text()) == state
    assert report.read_text() == "Retained failed trial and next action.\n"
    assert not (record.parent.parent / "baseline.json").exists()


def test_next_experiment_discovers_accepted_baseline_without_reusing_results(project):
    record, state = start(project)
    state.update(stage="complete", next_action="Start another experiment.")
    state["decisions"].append(
        {"outcome": "keep", "reason": "Fixture comparison accepted."}
    )
    record.write_text(json.dumps(state))
    accepted = {"experiment": state["id"], "source": state["starting_source"]}
    (record.parent.parent / "baseline.json").write_text(json.dumps(accepted))
    (project / "source.txt").write_text("later source changes\n")
    _, second = start(project, "optional-procedures")
    assert second["baseline"] == {
        "source": accepted["source"],
        "accepted_experiment": accepted["experiment"],
    }
    assert second["starting_source"] != second["baseline"]["source"]
    assert second["evidence"] == []
    result = call(project, "status")
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)["experiments"]) == 2


@pytest.mark.parametrize("name", ["../escape", "two/parts", "--bad", "Upper", ""])
def test_invalid_ids_cannot_write_outside_the_notebook(project, name):
    result = call(project, "start", name, "--idea", "An improvement")
    assert result.returncode != 0
    assert not (project / ".claude").exists()


def test_symlinked_runtime_directory_cannot_escape_project(project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / ".claude").symlink_to(outside, target_is_directory=True)
    result = call(project, "start", "escape", "--idea", "An improvement")
    assert result.returncode == 2 and "inside the project" in result.stderr
    assert list(outside.iterdir()) == []


def test_missing_or_corrupt_notebook_has_actionable_nonzero_status(project):
    result = call(project, "status")
    assert result.returncode == 0
    assert json.loads(result.stdout)["experiments"] == []
    result = call(project, "status", "unknown")
    assert result.returncode == 2 and "Notebook error" in result.stderr
    record, state = start(project)
    state["next_action"] = ""
    record.write_text(json.dumps(state))
    result = call(project, "status")
    assert result.returncode == 2 and "next_action" in result.stderr


def test_invalid_baseline_does_not_create_a_partial_notebook(project):
    directory = project / ".claude/improvements"
    directory.mkdir(parents=True)
    (directory / "baseline.json").write_text('{"experiment":"old","source":null}')
    result = call(project, "start", "new", "--idea", "An improvement")
    assert result.returncode == 2 and "source fingerprint" in result.stderr
    assert not (directory / "new").exists()


@pytest.mark.parametrize("case", ["improvement-prepare", "improvement-resume"])
def test_native_case_scaffolds_have_observable_verification(tmp_path, case):
    subprocess.run(
        ["bash", str(ROOT / "evals" / case / "fixture.sh")],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    result = subprocess.run(
        [sys.executable, "check.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if case == "improvement-prepare":
        assert result.returncode == 0, result.stderr
        record, state = start(tmp_path)
        assert state["stage"] == "prepare" and record.exists()
    else:
        assert result.returncode == 1 and "PRODUCT_CHECK_FAILED" in result.stdout
        directory = tmp_path / ".claude/improvements/context-loading"
        assert (
            "PRODUCT_CHECK_PASSED" in (directory / "evidence/baseline.log").read_text()
        )
        assert (
            "PRODUCT_CHECK_FAILED" in (directory / "evidence/candidate.log").read_text()
        )
        record = directory / "experiment.json"
        original = record.read_bytes()
        status = call(tmp_path, "status", "context-loading")
        assert status.returncode == 0, status.stderr
        assert json.loads(status.stdout)["experiments"][0]["stage"] == "compare"
        assert record.read_bytes() == original
        assert not (directory.parent / "baseline.json").exists()
