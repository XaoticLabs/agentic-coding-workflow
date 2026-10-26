"""Exercise model routing, actual command evidence and private environment staging."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "project with 'quotes'"
    (path / ".claude").mkdir(parents=True)
    (path / ".gitignore").write_text(".claude/\n.env\n")
    (path / "source.txt").write_text("original")
    for args in (
        ("init", "--quiet"),
        ("add", "."),
        (
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--quiet",
            "-m",
            "initial",
        ),
    ):
        subprocess.run(["git", *args], cwd=path, check=True)
    return path


def call(script, *args, **kwargs):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *map(str, args)],
        text=True,
        capture_output=True,
        timeout=20,
        **kwargs,
    )


def test_model_precedence_and_native_default():
    selection = module("workflow_models").selection
    assert selection("build", {})["requested"] is None
    environment = {
        "ANTHROPIC_MODEL": "native-id",
        "WORKFLOW_MODEL": "best",
        "WORKFLOW_EVALUATOR_MODEL": "judge-id",
    }
    assert selection("build", environment)["requested"] == "best"
    assert selection("evaluator", environment)["requested"] == "judge-id"
    assert (
        selection("merge", {"ANTHROPIC_MODEL": "native-id"})["requested"] == "native-id"
    )
    with pytest.raises(ValueError):
        selection("build", {"WORKFLOW_MODEL": "--bad value"})


def test_extended_project_commands_survive_legacy_initialization(project):
    config = project / ".claude/project-commands.json"
    config.write_text('{"install":"npm ci","health":null}')
    result = call(
        "project-commands.py", "init", project, "build", "test", "lint", "format", "run"
    )
    assert result.returncode == 0, result.stderr
    commands = json.loads(config.read_text())
    assert commands["install"] == "npm ci" and commands["health"] is None
    assert commands["test"] == "test"


def test_model_policy_survives_stale_tmux_environment(tmp_path):
    launcher = tmp_path / "launcher.sh"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; write_workflow_model_environment > "$2"',
            "bash",
            str(ROOT / "scripts/lib/claude-runner.sh"),
            str(launcher),
        ],
        env={"PATH": os.environ["PATH"], "WORKFLOW_MODEL": "best"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; printf "%s:%s" "$WORKFLOW_MODEL" "${WORKFLOW_EVALUATOR_MODEL-unset}"',
            "bash",
            str(launcher),
        ],
        env={"PATH": os.environ["PATH"], "WORKFLOW_EVALUATOR_MODEL": "stale"},
        capture_output=True,
        text=True,
    )
    assert result.stdout == "best:unset"


def test_experiments_capture_real_failures_and_escape_html(project, tmp_path):
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "version": 1,
                "experiments": [
                    {
                        "name": "<script>bad</script>",
                        "criterion": "process exits zero",
                        "command": [
                            sys.executable,
                            "-c",
                            "print('observed'); raise SystemExit(7)",
                        ],
                    },
                    {
                        "name": "control",
                        "criterion": "process exits zero",
                        "command": [sys.executable, "-c", "print('control')"],
                        "runs": 2,
                    },
                ],
            }
        )
    )
    output = tmp_path / "results"
    result = call(
        "run-experiments.py", matrix, "--project-dir", project, "--output-dir", output
    )
    assert result.returncode == 1, result.stderr
    report = json.loads((output / "results.json").read_text())
    assert report["status"] == "FAILED" and report["comparison_valid"]
    failed = report["experiments"][0]["trials"][0]
    assert failed["exit_code"] == 7 and failed["outcome"] == "failed"
    assert Path(failed["stdout"]).read_text().strip() == "observed"
    assert (
        "&lt;script&gt;bad&lt;/script&gt;" in (output / "comparison.html").read_text()
    )


def test_experiment_timeout_and_source_mutation_invalidate_comparison(
    project, tmp_path
):
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "version": 1,
                "experiments": [
                    {
                        "name": "mutation",
                        "criterion": "writes candidate",
                        "command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('source.txt').write_text('changed')",
                        ],
                    },
                    {
                        "name": "timeout",
                        "criterion": "finishes in time",
                        "command": [
                            sys.executable,
                            "-c",
                            "import time; time.sleep(30)",
                        ],
                        "timeout_seconds": 0.1,
                    },
                ],
            }
        )
    )
    result = call(
        "run-experiments.py",
        matrix,
        "--project-dir",
        project,
        "--output-dir",
        tmp_path / "results",
    )
    assert result.returncode == 1
    report = json.loads((tmp_path / "results/results.json").read_text())
    assert not report["comparison_valid"]
    assert report["experiments"][1]["trials"][0]["outcome"] == "timeout"


def test_observations_forward_target_as_data_and_preserve_failure(project, tmp_path):
    (project / ".claude/project-commands.json").write_text(
        json.dumps(
            {"health": 'printf "%s" "$WORKFLOW_TARGET"', "deploy_status": "exit 3"}
        )
    )
    result = call(
        "observe-project.py",
        "--project-dir",
        project,
        "--target",
        "staging; touch forbidden",
        "--actions",
        "health",
        "deploy_status",
        "--output-dir",
        tmp_path / "observations",
    )
    assert result.returncode == 1, result.stderr
    report = json.loads((tmp_path / "observations/observations.json").read_text())
    assert report["status"] == "NEEDS_ATTENTION"
    assert (
        Path(report["observations"][0]["stdout"]).read_text()
        == "staging; touch forbidden"
    )
    assert not (project / "forbidden").exists()


@pytest.mark.parametrize("action", [None, ""])
def test_missing_or_disabled_observation_never_passes(project, action):
    (project / ".claude/project-commands.json").write_text(
        json.dumps({"health": action})
    )
    result = call(
        "observe-project.py",
        "--project-dir",
        project,
        "--target",
        "staging",
        "--actions",
        "health",
    )
    assert result.returncode == 2 and "missing, disabled" in result.stderr


def test_environment_stages_current_source_without_secrets_or_host_git(
    project, tmp_path
):
    environment = module("project-environment")
    (project / "source.txt").write_text("current edits")
    (project / ".env").write_text("PRIVATE")
    workspace = tmp_path / "run/workspace"
    workspace.mkdir(parents=True)
    environment.stage_source(project, workspace, [])
    assert (workspace / "source.txt").read_text() == "current edits"
    assert not (workspace / ".git").exists() and not (workspace / ".env").exists()
    assert (project / "source.txt").read_text() == "current edits"
    with pytest.raises(ValueError):
        environment.stage_source(project, workspace, [".env"])
    (project / "escape").symlink_to("/tmp")
    with pytest.raises(ValueError):
        environment.stage_source(project, workspace, [])


def test_environment_dry_run_uses_private_mounts_and_required_actions(
    project, tmp_path
):
    config = {"version": 1, "image": "example/image@sha256:" + "a" * 64}
    (project / ".claude/project-environment.json").write_text(json.dumps(config))
    (project / ".claude/project-commands.json").write_text(
        '{"test":"python3 -m unittest"}'
    )
    output = tmp_path / "environment"
    result = call(
        "project-environment.py",
        "--project-dir",
        project,
        "--output-dir",
        output,
        "--dry-run",
        "--actions",
        "test",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "run.json").read_text())
    assert report["status"] == "NOT_RUN"
    command = report["command"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--pids-limit" in command
    assert str(project) not in " ".join(command)
    assert (output / "workspace/source.txt").is_file()
    result = call(
        "project-environment.py",
        "--project-dir",
        project,
        "--dry-run",
        "--actions",
        "lint",
    )
    assert result.returncode == 2 and "required action lint" in result.stderr


@pytest.mark.parametrize(
    "change",
    [
        {"image": "example:latest"},
        {"network": "host"},
        {"cpus": 0},
        {"pass_env": ["HOME"]},
        {"pids_limit": True},
    ],
)
def test_invalid_environment_profiles_fail_before_execution(tmp_path, change):
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps({"version": 1, "image": "sha256:" + "a" * 64, **change}))
    with pytest.raises(ValueError):
        module("project-environment").recipe(path)


def test_eval_dry_run_records_both_arms_and_never_consumes_holdout(tmp_path):
    output = tmp_path / "eval"
    result = call(
        "run-evals.py",
        "--split",
        "tuning",
        "--model",
        "execution-id",
        "--judge-model",
        "judge-id",
        "--max-cost-usd",
        "5",
        "--output-dir",
        output,
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "run.json").read_text())
    assert report["status"] == "NOT_RUN"
    assert report["command"][report["command"].index("--tag") + 1] == "tuning"
    assert "with-without" in report["command"] and "--no-publish" in report["command"]
    result = call(
        "run-evals.py",
        "--split",
        "holdout",
        "--model",
        "id",
        "--judge-model",
        "id",
        "--max-cost-usd",
        "5",
        "--dry-run",
    )
    assert result.returncode == 2 and "frozen-revision" in result.stderr


def test_eval_auth_preflight_never_starts_paid_runs(tmp_path):
    binary = tmp_path / "bin/claude"
    binary.parent.mkdir()
    binary.write_text(
        '#!/usr/bin/env bash\nif [ "$1" = --version ]; then echo \'2.1.310\'; elif [ "$1" = auth ]; then echo \'{"loggedIn":false}\'; else touch "$UNEXPECTED_PAID_CALL"; fi\n'
    )
    binary.chmod(0o755)
    output = tmp_path / "eval"
    unexpected = tmp_path / "unexpected"
    result = call(
        "run-evals.py",
        "--split",
        "tuning",
        "--model",
        "best",
        "--judge-model",
        "best",
        "--max-cost-usd",
        "5",
        "--output-dir",
        output,
        env={
            **os.environ,
            "PATH": f"{binary.parent}:{os.environ['PATH']}",
            "UNEXPECTED_PAID_CALL": str(unexpected),
        },
    )
    report = json.loads((output / "run.json").read_text())
    assert result.returncode == 2 and report["status"] == "NOT_RUN"
    assert "not authenticated" in report["reason"] and not unexpected.exists()


def test_native_behavior_fixture_detects_bug_and_accepts_real_fix(tmp_path):
    fixture = ROOT / "evals/runtime-proof-regression/fixture.sh"
    subprocess.run(["bash", str(fixture)], cwd=tmp_path, check=True)
    verification = (tmp_path / "verify_pages.py").read_bytes()
    baseline = subprocess.run(
        [sys.executable, "verify_pages.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert baseline.returncode == 1 and "BEHAVIOR_CHECK_FAILED" in baseline.stdout
    (tmp_path / "pages.py").write_text(
        "def page(items, offset, size):\n    return items[offset:offset + size]\n"
    )
    fixed = subprocess.run(
        [sys.executable, "verify_pages.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert fixed.returncode == 0 and "BEHAVIOR_CHECK_PASSED" in fixed.stdout
    assert (tmp_path / "verify_pages.py").read_bytes() == verification


def test_native_missing_runtime_fixture_really_fails(tmp_path):
    subprocess.run(
        ["bash", str(ROOT / "evals/unavailable-runtime-proof/fixture.sh")],
        cwd=tmp_path,
        check=True,
    )
    command = json.loads((tmp_path / ".claude/project-commands.json").read_text())[
        "test"
    ]
    result = subprocess.run(
        ["bash", "-o", "pipefail", "-c", command],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 127
    assert "workflow-missing-integration-runtime-8b4f" in result.stderr


def test_environment_engine_failure_retains_error_without_host_fallback(
    project, tmp_path
):
    binary = tmp_path / "bin/podman"
    binary.parent.mkdir()
    binary.write_text("#!/usr/bin/env bash\nexit 125\n")
    binary.chmod(0o755)
    (project / ".claude/project-environment.json").write_text(
        json.dumps({"version": 1, "image": "sha256:" + "a" * 64})
    )
    (project / ".claude/project-commands.json").write_text(
        '{"test":"touch forbidden-host-write"}'
    )
    output = tmp_path / "environment"
    result = call(
        "project-environment.py",
        "--project-dir",
        project,
        "--output-dir",
        output,
        "--actions",
        "test",
        env={**os.environ, "PATH": f"{binary.parent}:{os.environ['PATH']}"},
    )
    report = json.loads((output / "run.json").read_text())
    assert result.returncode == 2 and report["status"] == "ERROR"
    assert report["execution"]["exit_code"] == 125
    assert not (project / "forbidden-host-write").exists()


def test_environment_recipe_changes_invalidate_source_evidence(project):
    execution = module("workflow_execution")
    before = execution.source_state(project)
    (project / ".claude/project-environment.json").write_text('{"version":1}')
    assert execution.source_state(project) != before


def test_real_stream_processor_retains_observed_model_ids(tmp_path):
    trace = tmp_path / "trace.jsonl"
    events = [
        {"type": "system", "subtype": "init", "model": "init-id"},
        {"type": "assistant", "message": {"model": "answer-id", "content": []}},
        {"type": "result", "modelUsage": {"answer-id": {}}},
    ]
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills/ralph/scripts/stream-processor.py"),
            "--trace-file",
            str(trace),
            "--quiet",
        ],
        input="\n".join(map(json.dumps, events)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    observed = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [
        (event["model"], event["source"])
        for event in observed
        if event["type"] == "model"
    ] == [
        ("init-id", "cli_init"),
        ("answer-id", "assistant"),
        ("answer-id", "cli_result"),
    ]
