"""Exercise arguments across foreground and tmux process boundaries."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o755)


@pytest.fixture
def launch_environment(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    plugin = tmp_path / "plugin's files"
    scripts = plugin / "skills/ralph/scripts"
    scripts.mkdir(parents=True)
    for name in ("launch.sh", "options.sh"):
        shutil.copy2(ROOT / "skills/ralph/scripts" / name, scripts / name)
    (scripts / "generate-agents-md.sh").write_text("exit 0\n")
    for name in ("loop.sh", "orchestrate-parallel.sh"):
        (scripts / name).write_text('exec python3 "$TEST_RECORDER" "$0" "$@"\n')
    executable(
        tmp_path / "recorder.py",
        """
import json, os, sys
with open(os.environ['TEST_CALLS'], 'a') as output:
    output.write(json.dumps({'argv': sys.argv[1:], 'env': {
        key: os.environ.get(key) for key in (
            'CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT', 'RALPH_EVAL_PER_ITER',
            'RALPH_EVAL_END_OF_RUN', 'RALPH_PARALLEL_EVAL',
        )
    }}) + '\\n')
""",
    )
    executable(
        tmp_path / "bin/tmux",
        """
import json, os, subprocess, sys
with open(os.environ['TEST_TMUX_CALLS'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'has-session':
    sys.exit(1)
if sys.argv[1] in ('new-session', 'new-window'):
    # Simulate a pre-existing tmux server that did not inherit this launch's env.
    env = {key: value for key, value in os.environ.items() if not key.startswith('RALPH_')}
    sys.exit(subprocess.run(sys.argv[-2:], env=env).returncode)
""",
    )
    project = tmp_path / "project's files"
    (project / ".claude/specs/feature").mkdir(parents=True)
    (project / ".claude/specs/feature/IMPLEMENTATION_PLAN.md").write_text("plan")
    environment = {
        **os.environ,
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "CLAUDE_PROJECT_DIR": str(project),
        "CLAUDE_PLUGIN_ROOT": str(plugin),
        "TEST_RECORDER": str(tmp_path / "recorder.py"),
        "TEST_CALLS": str(tmp_path / "calls.jsonl"),
        "TEST_TMUX_CALLS": str(tmp_path / "tmux.jsonl"),
        "TMUX": "",
        "RALPH_EVAL_PER_ITER": "false",
        "RALPH_EVAL_END_OF_RUN": "true",
        "RALPH_PARALLEL_EVAL": "end",
    }
    return scripts / "launch.sh", project, environment


@pytest.mark.parametrize("inside_tmux", [False, True])
@pytest.mark.parametrize("mode", ["once", "tmux", "parallel"])
@pytest.mark.parametrize("evaluation", ["--no-eval", "--eval-per-iter"])
def test_ralph_options_survive_every_launch_path(
    launch_environment: tuple[Path, Path, dict[str, str]],
    inside_tmux: bool,
    mode: str,
    evaluation: str,
) -> None:
    launcher, project, environment = launch_environment
    environment["TMUX"] = "existing" if inside_tmux else ""
    mode_flags = {"once": ["--once"], "tmux": [], "parallel": ["--parallel", "3"]}[mode]
    gate = ["--eval-gates-merge"] if evaluation == "--eval-per-iter" else []
    result = subprocess.run(
        [
            "bash",
            str(launcher),
            ".claude/specs/feature",
            *mode_flags,
            "--max",
            "7",
            "--clean-room",
            "--time-budget",
            "42",
            "--checkpoint-every=2",
            evaluation,
            *gate,
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [
        json.loads(line)
        for line in Path(environment["TEST_CALLS"]).read_text().splitlines()
    ]
    assert len(calls) == 1
    call = calls[0]
    arguments = call["argv"]
    expected_script = "orchestrate-parallel.sh" if mode == "parallel" else "loop.sh"
    assert Path(arguments[0]).name == expected_script
    assert arguments[1] == str(project / ".claude/specs/feature")
    assert "--time-budget=42" in arguments
    assert "--checkpoint-every=2" in arguments
    assert "--clean-room" in arguments
    assert evaluation in arguments
    assert ("--eval-gates-merge" in arguments) == bool(gate)
    assert arguments[2:4] == (
        ["feature", "3"]
        if mode == "parallel"
        else ["build", "1" if mode == "once" else "7"]
    )
    assert call["env"]["CLAUDE_PROJECT_DIR"] == str(project)
    if evaluation == "--no-eval":
        assert call["env"]["RALPH_EVAL_PER_ITER"] == "false"
        assert call["env"]["RALPH_EVAL_END_OF_RUN"] == "false"
        assert call["env"]["RALPH_PARALLEL_EVAL"] == "off"
    else:
        assert call["env"]["RALPH_EVAL_PER_ITER"] == "true"
    if mode != "once":
        tmux_calls = [
            json.loads(line)
            for line in Path(environment["TEST_TMUX_CALLS"]).read_text().splitlines()
        ]
        assert tmux_calls[-1][0] == ("new-window" if inside_tmux else "new-session")


@pytest.mark.parametrize("action", ["--plan", "--harvest"])
def test_planning_and_harvest_use_the_same_options(
    launch_environment: tuple[Path, Path, dict[str, str]],
    action: str,
) -> None:
    launcher, project, environment = launch_environment
    result = subprocess.run(
        [
            "bash",
            str(launcher),
            ".claude/specs/feature",
            action,
            "--time-budget=12",
            "--no-eval",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    arguments = json.loads(Path(environment["TEST_CALLS"]).read_text())["argv"]
    assert arguments[2:4] == [action.removeprefix("--"), "1"]
    assert "--time-budget=12" in arguments
    assert "--no-eval" in arguments


@pytest.mark.parametrize(
    "flags",
    [
        ["--time-budget"],
        ["--checkpoint-every=0"],
        ["--max=-1"],
        ["--parallel=7"],
        ["--parallel=2", "--once"],
        ["--no-eval", "--eval-per-iter"],
        ["--no-eval", "--eval-gates-merge"],
        ["--time-budget=$(touch injected)"],
        ["--unknown"],
    ],
)
def test_invalid_options_fail_before_launch(
    launch_environment: tuple[Path, Path, dict[str, str]],
    flags: list[str],
) -> None:
    launcher, project, environment = launch_environment
    result = subprocess.run(
        ["bash", str(launcher), ".claude/specs/feature", *flags],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stderr
    assert not Path(environment["TEST_CALLS"]).exists()
    assert not (project / "injected").exists()


def test_tmux_helper_passes_context_and_prompt_as_data(tmp_path: Path) -> None:
    executable(
        tmp_path / "bin/claude",
        """
import json, os, sys
from pathlib import Path
Path(os.environ['TEST_CLAUDE_CALL']).write_text(json.dumps({'argv': sys.argv[1:], 'input': sys.stdin.read()}))
""",
    )
    executable(
        tmp_path / "bin/tmux",
        """
import os, subprocess, sys
if sys.argv[1] == 'split-window':
    # Remove only the terminal-holding suffix so the regression test can exit.
    command = sys.argv[-1].split("; echo '--- Claude finished ---'", 1)[0]
    sys.exit(subprocess.run(['bash', '-c', command], env=os.environ).returncode)
""",
    )
    context = tmp_path / "context's $(touch injected).txt"
    context.write_text('context with "quotes" and $shell syntax\n')
    prompt = "Review 'quoted' context; $(touch injected) `touch injected`"
    output = tmp_path / "result with 'quotes'.json"
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "skills/tmux-multiplexer/scripts/launch-claude-pane.sh"),
            prompt,
            "--context",
            str(context),
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "TMUX": "existing",
            "TEST_CLAUDE_CALL": str(output),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text()) == {
        "argv": ["-p", prompt],
        "input": context.read_text(),
    }
    assert not (tmp_path / "injected").exists()
