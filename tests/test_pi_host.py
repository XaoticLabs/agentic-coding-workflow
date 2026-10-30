"""Generated Pi resources and installed-host policy, without paid inference."""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def renderer():
    spec = importlib.util.spec_from_file_location(
        "host_render_pi", ROOT / "scripts/host_render_pi.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(source: str, **metadata) -> dict:
    return {
        "source": source,
        "description": "Fixture: quoted description",
        "body": "Use scripts/check.sh\n",
        "user_invocable": True,
        "model_invocable": True,
        **metadata,
    }


def test_pi_generation_preserves_resources_and_invocation_policy(tmp_path: Path):
    skill = tmp_path / "skills/example"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("canonical")
    script = skill / "scripts/check.sh"
    script.write_text(
        '#!/bin/bash\nprintf "%s\\n" "${BASH_SOURCE[0]}" "$WORKFLOW_HOST"\nexit 0\n'
    )
    python_script = skill / "scripts/check.py"
    python_script.write_text(
        "#!/usr/bin/env python3\nfrom pathlib import Path\nprint(Path(__file__).resolve())\n"
    )
    (skill / "assets").mkdir()
    (skill / "assets/image.bin").write_bytes(b"\x00\xff\x80")
    catalog = {
        "commands": {"ship": entry("commands/ship.md", model_invocable=False)},
        "skills": {
            "example": entry("skills/example/SKILL.md"),
            "model-only": entry("skills/model-only/SKILL.md", user_invocable=False),
        },
    }
    output = renderer().generate(tmp_path, catalog)
    assert (
        "disable-model-invocation: true"
        in output["hosts/pi/generated/skills/ship/SKILL.md"]
    )
    assert "hosts/pi/generated/model-skills/model-only/SKILL.md" in output
    assert "hosts/pi/generated/skills/model-only/SKILL.md" not in output
    assert (
        output["hosts/pi/generated/skills/example/assets/image.bin"] == b"\x00\xff\x80"
    )
    wrappers = []
    for name in ("check.sh", "check.py"):
        relative = f"hosts/pi/generated/skills/example/scripts/{name}"
        generated = tmp_path / relative
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text(output[relative])
        wrappers.append(generated)
    shell = subprocess.run(
        ["bash", str(wrappers[0])],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert Path(shell.stdout.splitlines()[0]).resolve() == script.resolve()
    assert shell.stdout.splitlines()[1] == "pi"
    python = subprocess.run(
        [sys.executable, str(wrappers[1])],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert Path(python.stdout.strip()) == python_script.resolve()
    script.write_text("#!/bin/bash\nexit 1\n")
    assert subprocess.run(["bash", str(wrappers[0])], timeout=5).returncode == 1


def pi_module() -> Path | None:
    executable = shutil.which("pi")
    if not executable:
        return None
    for directory in Path(executable).resolve().parents:
        manifest = directory / "package.json"
        if (
            manifest.is_file()
            and json.loads(manifest.read_text()).get("name")
            == "@earendil-works/pi-coding-agent"
        ):
            return directory / "dist/index.js"
    return None


def test_pi_transport_and_policy_helpers():
    node = supported_node()
    result = subprocess.run(
        [node, "--experimental-strip-types", "hosts/pi/core.test.mjs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert "tests 7" in result.stdout and "fail 0" in result.stdout, (
        result.stdout + result.stderr
    )


def supported_node() -> str:
    node = shutil.which("node")
    version = None
    if node:
        result = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=5
        )
        match = re.match(r"v(\d+)\.(\d+)\.(\d+)", result.stdout.strip())
        if match:
            version = tuple(map(int, match.groups()))
    if node and version and version >= (22, 19, 0):
        return node
    message = (
        f"Pi checks require Node >=22.19.0; found {version or 'no supported Node'}"
    )
    if os.environ.get("WORKFLOW_REQUIRE_PI") == "1":
        pytest.fail(message)
    pytest.skip(message)


@pytest.mark.parametrize("required", [False, True])
def test_older_node_does_not_become_a_claude_development_requirement(
    tmp_path: Path, monkeypatch, required: bool
):
    node = tmp_path / "node18"
    node.write_text("#!/bin/sh\nprintf 'v18.20.0\\n'\n")
    node.chmod(0o755)
    monkeypatch.setattr(
        shutil, "which", lambda name: str(node) if name == "node" else None
    )
    if required:
        monkeypatch.setenv("WORKFLOW_REQUIRE_PI", "1")
    else:
        monkeypatch.delenv("WORKFLOW_REQUIRE_PI", raising=False)
    exception = pytest.fail.Exception if required else pytest.skip.Exception
    with pytest.raises(exception, match="Node >=22.19.0"):
        supported_node()


@pytest.mark.parametrize(
    "worker,mode", [(False, "tui"), (False, "json"), (True, "json")]
)
def test_installed_pi_loads_adapter_and_enforces_policy(
    tmp_path: Path, worker: bool, mode: str
):
    module = pi_module()
    if not module:
        if os.environ.get("WORKFLOW_REQUIRE_PI") == "1":
            pytest.fail(
                "Pi native checks are required but the installed module was not found"
            )
        pytest.skip("Pi is not installed; run maak check-hosts in the host environment")
    node = supported_node()
    project = tmp_path / "project with spaces"
    project.mkdir()
    (project / "fixture.txt").write_text("safe fixture\n")
    (project / ".gitignore").write_text(".claude/\n")
    for args in (
        ["init", "--quiet"],
        ["config", "user.name", "Fixture"],
        ["config", "user.email", "fixture@example.com"],
        ["add", "."],
        ["commit", "--quiet", "-m", "fixture"],
    ):
        subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)
    (project / ".claude").mkdir()
    (project / ".claude/project-commands.json").write_text(
        json.dumps({"lint": "exit 1", "test": "true"})
    )
    desktop = tmp_path / "desktop-bin/osascript"
    desktop.parent.mkdir()
    notification_log = tmp_path / "desktop-notifications.jsonl"
    desktop.write_text(
        '#!/usr/bin/env python3\nimport json, os, sys\nwith open(os.environ["WORKFLOW_PI_SMOKE_NOTIFICATIONS"], "a") as stream: stream.write(json.dumps(sys.argv[-2:]) + "\\n")\n'
    )
    desktop.chmod(0o755)
    environment = {
        **os.environ,
        "WORKFLOW_PI_MODULE": str(module),
        "WORKFLOW_PI_SMOKE_PROJECT": str(project),
        "WORKFLOW_HOST_WORKER": "1" if worker else "0",
        "WORKFLOW_HOST_ROLE": "evaluator" if worker else "",
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "pi-user"),
        "WORKFLOW_PI_SMOKE_MODE": mode,
        "PATH": f"{desktop.parent}{os.pathsep}{os.environ['PATH']}",
        "WORKFLOW_PI_SMOKE_NOTIFICATIONS": str(notification_log),
        "WORKFLOW_NOTIFY": "true",
        "RELAY_MODE": "0",
    }
    result = subprocess.run(
        [node, "hosts/pi/smoke.mjs"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["policy"] == "passed"
