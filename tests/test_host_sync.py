"""One canonical edit must propagate, with host policy and hook behavior intact."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from host_bridge import expand_text, hook_event, render  # noqa: E402
from host_catalog import build_catalog  # noqa: E402


def synchronizer():
    spec = importlib.util.spec_from_file_location(
        "sync_hosts", ROOT / "scripts/sync-hosts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sources(tmp_path: Path) -> Path:
    for name in ("commands", "skills", "agents", "references", "hooks", "scripts"):
        shutil.copytree(
            ROOT / name,
            tmp_path / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    return tmp_path


def test_one_source_edit_updates_both_hosts_and_drift_is_read_only(sources: Path):
    sync = synchronizer()
    sync.synchronize(sources)
    command = sources / "commands/test.md"
    command.write_text(command.read_text() + "\nCanonical command change.\n")
    before = (sources / "hosts/catalog.json").read_bytes()
    differences = sync.synchronize(sources, check=True)
    assert "hosts/catalog.json" in differences
    assert "hosts/pi/generated/skills/test/SKILL.md" in differences
    assert "hosts/autolith/skills/test/SKILL.md" in differences
    assert (sources / "hosts/catalog.json").read_bytes() == before
    sync.synchronize(sources)
    for path in (
        "hosts/pi/generated/skills/test/SKILL.md",
        "hosts/autolith/skills/test/SKILL.md",
    ):
        assert "Canonical command change." in (sources / path).read_text()
    assert sync.synchronize(sources, check=True) == []


def test_binary_resources_and_removed_workflows_propagate_without_deleting_unowned_files(
    sources: Path,
):
    sync = synchronizer()
    asset = sources / "skills/improve-workflow/assets/fixture.bin"
    asset.write_bytes(b"\x00\xff\x80")
    sync.synchronize(sources)
    for path in (
        "hosts/pi/generated/skills/improve-workflow/assets/fixture.bin",
        "hosts/autolith/skills/improve-workflow/assets/fixture.bin",
    ):
        assert (sources / path).read_bytes() == asset.read_bytes()
    owned = sources / "hosts/pi/generated/skills/test/SKILL.md"
    unrelated = owned.parent / "notes.txt"
    unrelated.write_text("preserve this")
    (sources / "commands/test.md").unlink()
    sync.synchronize(sources)
    assert not owned.exists()
    assert unrelated.read_text() == "preserve this"


def test_generated_file_symlink_cannot_overwrite_canonical_source(sources: Path):
    sync = synchronizer()
    sync.synchronize(sources)
    canonical = sources / "commands/test.md"
    before = canonical.read_bytes()
    generated = sources / "hosts/pi/generated/skills/test/SKILL.md"
    generated.unlink()
    generated.symlink_to(canonical)
    sync.synchronize(sources)
    assert canonical.read_bytes() == before
    assert not generated.is_symlink()


def test_yaml_metadata_is_parsed_and_ambiguous_policy_is_rejected(sources: Path):
    command = sources / "commands/test.md"
    command.write_text(
        '---\ndescription: >-\n  A multiline: description\n  with punctuation.\nallowed-tools: [Read, "Bash(git status *)"]\ndisable-model-invocation: true\n---\nBody\n'
    )
    entry = build_catalog(sources)["commands"]["test"]
    assert entry["description"] == "A multiline: description with punctuation."
    assert entry["allowed_tools"] == ["Read", "Bash(git status *)"]
    assert entry["model_invocable"] is False
    command.write_text(
        "---\ndescription: test\nuser-invocable: true\nuser-invocable: false\n---\nBody\n"
    )
    with pytest.raises(ValueError, match="Duplicate"):
        build_catalog(sources)


def test_renderer_expands_roots_arguments_and_native_names_without_executing_arguments(
    sources: Path, tmp_path: Path
):
    sync = synchronizer()
    sync.synchronize(sources)
    arguments = "!`touch should-not-exist` $ARGUMENTS"
    result = render("pi", "command", "test", arguments, tmp_path, sources)
    assert arguments in result["prompt"]
    assert str(sources / "references/shared-patterns.md") in result["prompt"]
    assert not (tmp_path / "should-not-exist").exists()
    assert "${CLAUDE_PLUGIN_ROOT}" not in result["prompt"]
    assert "/workflow-test" in expand_text(
        "/agentic-coding-workflow:test", "autolith", tmp_path
    )
    with pytest.raises(ValueError, match="Unknown command"):
        render("pi", "command", "missing", "", tmp_path, sources)


@pytest.mark.parametrize("quoted", [False, True])
def test_prime_dynamic_context_runs_before_prompt_submission(
    tmp_path: Path, quoted: bool
):
    root = tmp_path / "package with spaces"
    (root / "hosts").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts/context.sh").write_text("printf 'CURRENT CONTEXT'\n")
    context = (
        '!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/context.sh"`'
        if quoted
        else "!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/context.sh`"
    )
    (root / "hosts/catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "commands": {
                    "prime": {
                        "body": context + "\n$ARGUMENTS",
                        "source": "commands/prime.md",
                    }
                },
            }
        )
    )
    prompt = render("pi", "command", "prime", "user input", tmp_path, root)["prompt"]
    assert "CURRENT CONTEXT\nuser input" in prompt
    assert "!`bash" not in prompt


@pytest.mark.parametrize("host", ["pi", "autolith"])
def test_native_session_examples_dispatch_to_selected_host(host: str, tmp_path: Path):
    text = expand_text(
        "`claude --worktree example --tmux` and `claude --resume saved-feature`\ncommand -v claude\n"
        "`claude --plugin-dir /path/to/plugin --agent agentic-coding-workflow:evaluator`",
        host,
        tmp_path,
    )
    assert f"spawn-session.sh implementer --host {host} --worktree example" in text
    assert f"spawn-session.sh --host {host} --resume saved-feature" in text
    assert f"command -v {host}" in text
    assert f"spawn-session.sh evaluator --host {host}" in text
    assert "--tmux" not in text


def test_generated_executable_resources_keep_the_canonical_layout(sources: Path):
    sync = synchronizer()
    sync.synchronize(sources)
    for directory in ("hosts/pi/generated/skills", "hosts/autolith/skills"):
        script = sources / directory / "improve-workflow/scripts/notebook.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "start" in result.stdout


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for command in (
        ["init", "--quiet"],
        ["config", "user.name", "Fixture"],
        ["config", "user.email", "fixture@example.com"],
    ):
        subprocess.run(["git", *command], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text(".claude/\n")
    (tmp_path / "source.py").write_text("value = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "fixture"], cwd=tmp_path, check=True
    )
    (tmp_path / ".claude").mkdir()
    return tmp_path


def test_hook_bridge_preserves_real_block_repair_halt_and_new_turn_reset(project: Path):
    protected = hook_event(
        "PreToolUse",
        {
            "cwd": str(project),
            "session_id": "native-host",
            "tool_name": "Read",
            "tool_input": {"file_path": ".env"},
        },
    )
    assert protected["action"] == "repair"
    assert protected["outputs"][0]["exit_code"] == 2
    settings = project / ".claude/project-commands.json"
    settings.write_text(json.dumps({"lint": "false", "test": "true"}))
    payload = {"cwd": str(project), "session_id": "native-host"}
    for attempt in range(3):
        result = hook_event("Stop", {**payload, "stop_hook_active": attempt > 0})
        assert result["action"] == "repair"
        assert result["outputs"][-1]["exit_code"] == 0
    exhausted = hook_event("Stop", {**payload, "stop_hook_active": True})
    assert exhausted["action"] == "halt"
    assert "three attempts" in exhausted["reason"]
    settings.write_text(json.dumps({"lint": "true", "test": "true"}))
    assert (
        hook_event("Stop", {**payload, "stop_hook_active": False})["action"] == "allow"
    )


@pytest.mark.parametrize("fault", ["timeout", "exit", "invalid-json"])
def test_policy_hook_errors_fail_closed(tmp_path: Path, fault: str):
    (tmp_path / "hooks").mkdir()
    script = tmp_path / "hooks/check.sh"
    script.write_text(
        {"timeout": "sleep 2", "exit": "exit 7", "invalid-json": "printf invalid"}[
            fault
        ]
    )
    (tmp_path / "hooks/hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/check.sh"',
                                    "timeout": 0.05,
                                }
                            ]
                        }
                    ]
                }
            }
        )
    )
    assert hook_event("Stop", {"cwd": str(tmp_path)}, tmp_path)["action"] == "halt"
