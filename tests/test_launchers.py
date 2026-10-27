"""Exercise arguments across foreground and tmux process boundaries."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o755)


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


@pytest.mark.parametrize("isolated", [True, False])
def test_spawn_delegates_native_isolation_and_preserves_arguments(
    tmp_path: Path, isolated: bool
) -> None:
    record = tmp_path / "invocation.json"
    executable(
        tmp_path / "bin/claude",
        "import json, os, sys\nfrom pathlib import Path\n"
        "Path(os.environ['TEST_SPAWN']).write_text(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}))\n",
    )
    executable(
        tmp_path / "bin/tmux",
        "import subprocess, sys\n"
        "assert sys.argv[1] == 'split-window'\n"
        "sys.exit(subprocess.run(sys.argv[-3:]).returncode)\n",
    )
    # Any manual Git worktree creation would invoke this stub and fail the test.
    executable(tmp_path / "bin/git", "raise SystemExit('unexpected manual Git call')\n")
    context = tmp_path / "context's $(touch injected).txt"
    context.write_text("Review context\n")
    prompt = "Review 'quoted' context; $(touch injected) `touch injected`"
    flags = ["--worktree", "review-auth"] if isolated else []
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/spawn-session.sh"),
            "evaluator",
            *flags,
            "--context",
            context.name,
            "--",
            prompt,
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "TMUX": "" if isolated else "existing",
            "TEST_SPAWN": str(record),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = [
        "--plugin-dir",
        str(ROOT),
        "--agent",
        "agentic-coding-workflow:evaluator",
        *(["--name", "review-auth"] if isolated else []),
        *(["--worktree", "review-auth", "--tmux"] if isolated else []),
        f"Read the context file at {context} before starting.\n\n{prompt}",
    ]
    assert json.loads(record.read_text()) == {"argv": expected, "cwd": str(tmp_path)}
    assert not (tmp_path / "injected").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["../evaluator"],
        ["missing-role"],
        ["evaluator", "--worktree"],
        ["evaluator", "--context", "missing.txt"],
        ["evaluator", "--unknown"],
        ["implementer", "--goal", ""],
        ["implementer", "--goal", "   "],
        ["implementer", "--goal", "done", "another prompt"],
        ["implementer", "--goal", "x" * 4001],
        ["implementer", "--resume", "existing"],
        ["--resume"],
        ["--resume", "existing", "--worktree", "new"],
        ["--resume", "existing", "--name", "replacement"],
    ],
)
def test_spawn_rejects_invalid_input_without_launching(
    tmp_path: Path, arguments: list[str]
) -> None:
    record = tmp_path / "launched"
    executable(
        tmp_path / "bin/claude",
        f"from pathlib import Path\nPath({str(record)!r}).touch()\n",
    )
    executable(tmp_path / "bin/tmux", "raise SystemExit('unexpected tmux call')\n")
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/spawn-session.sh"), *arguments],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not record.exists()


@pytest.mark.parametrize("isolated", [True, False])
def test_native_goal_is_one_literal_prompt_with_context_and_a_persistent_name(
    tmp_path: Path, isolated: bool
) -> None:
    record = tmp_path / "goal.json"
    executable(
        tmp_path / "bin/claude",
        "import json, os, sys\nfrom pathlib import Path\n"
        "Path(os.environ['TEST_GOAL']).write_text(json.dumps({'argv': sys.argv[1:], 'relay_mode': os.environ.get('RELAY_MODE')}))\n",
    )
    executable(
        tmp_path / "bin/tmux",
        "import os, subprocess, sys\n"
        "assert sys.argv[1] == 'split-window'\n"
        "env = {**os.environ, 'RELAY_MODE': '1'}\n"
        "sys.exit(subprocess.run(sys.argv[-3:], env=env).returncode)\n",
    )
    executable(tmp_path / "bin/git", "raise SystemExit('unexpected Git call')\n")
    context = tmp_path / "context's $(touch injected).md"
    context.write_text("Acceptance criteria\n")
    condition = "The 'auth' tests pass; $(touch injected) `touch injected`"
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/spawn-session.sh"),
            "implementer",
            "--name",
            "auth-feature",
            *(["--worktree", "auth"] if isolated else []),
            "--context",
            context.name,
            "--goal",
            condition,
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "TMUX": "" if isolated else "existing",
            "RELAY_MODE": "1",
            "TEST_GOAL": str(record),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(record.read_text()) == {
        "argv": [
            "--plugin-dir",
            str(ROOT),
            "--agent",
            "agentic-coding-workflow:implementer",
            "--name",
            "auth-feature",
            *(["--worktree", "auth", "--tmux"] if isolated else []),
            f"/goal Read the context file at {context} before starting.\n\n{condition}",
        ],
        "relay_mode": "0",
    }
    assert not (tmp_path / "injected").exists()
    assert not (tmp_path / ".claude").exists()


@pytest.mark.parametrize("native_status", [0, 37])
@pytest.mark.parametrize("condition", [None, "The next related task is verified."])
def test_resume_keeps_the_native_session_and_propagates_failure_without_restart(
    tmp_path: Path, native_status: int, condition: str | None
) -> None:
    record = tmp_path / "resume.jsonl"
    executable(
        tmp_path / "bin/claude",
        "import json, os, sys\n"
        "assert os.environ.get('RELAY_MODE') == '0'\n"
        "with open(os.environ['TEST_RESUME'], 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(int(os.environ['TEST_NATIVE_STATUS']))\n",
    )
    executable(
        tmp_path / "bin/tmux", "raise SystemExit('resume must not launch tmux')\n"
    )
    executable(
        tmp_path / "bin/git", "raise SystemExit('resume must not create a worktree')\n"
    )
    session = "auth's $(touch injected)"
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/spawn-session.sh"),
            "--resume",
            session,
            *(["--goal", condition] if condition else []),
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "TMUX": "",
            "RELAY_MODE": "1",
            "TEST_RESUME": str(record),
            "TEST_NATIVE_STATUS": str(native_status),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == native_status, result.stderr
    assert [json.loads(line) for line in record.read_text().splitlines()] == [
        [
            "--plugin-dir",
            str(ROOT),
            "--resume",
            session,
            *([f"/goal {condition}"] if condition else []),
        ]
    ]
    assert not (tmp_path / "injected").exists()
