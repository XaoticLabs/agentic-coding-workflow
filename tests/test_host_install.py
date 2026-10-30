"""Pinned host installation preserves unrelated binaries and verifies releases."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def installer(tmp_path: Path, **variables) -> tuple[dict, Path, Path]:
    scripts = tmp_path / "bin"
    scripts.mkdir()
    calls = tmp_path / "npm-args.json"
    npm = scripts / "npm"
    npm.write_text(
        '#!/usr/bin/env python3\nimport json, os, pathlib, sys\npathlib.Path(os.environ["INSTALL_CALLS"]).write_text(json.dumps(sys.argv[1:]))\n'
    )
    npm.chmod(0o755)
    prefix = tmp_path / "prefix with spaces"
    environment = {
        **os.environ,
        "PATH": f"{scripts}:{os.environ['PATH']}",
        "INSTALL_CALLS": str(calls),
        **variables,
    }
    return environment, prefix, calls


def test_installer_uses_pinned_peer_host_and_links_existing_verified_release(
    tmp_path: Path,
):
    environment, prefix, calls = installer(tmp_path)
    versions = json.loads((ROOT / "hosts/versions.json").read_text())
    release = prefix / "share/autolith/releases" / versions["autolith"]
    (release / "bin").mkdir(parents=True)
    (release / "RELEASE").write_text(f"version={versions['autolith']}\n")
    (release / "bin/autolith").write_text("fixture")
    result = subprocess.run(
        ["bash", "scripts/install-hosts.sh", "--prefix", str(prefix)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    arguments = json.loads(calls.read_text())
    assert "--ignore-scripts" in arguments
    assert arguments[-1] == f"@earendil-works/pi-coding-agent@{versions['pi']}"
    assert (prefix / "bin/autolith").resolve() == release / "bin/autolith"


def test_installer_preserves_unmanaged_autolith_before_installing_anything(
    tmp_path: Path,
):
    environment, prefix, calls = installer(tmp_path)
    (prefix / "bin").mkdir(parents=True)
    executable = prefix / "bin/autolith"
    executable.write_text("user-owned executable")
    result = subprocess.run(
        ["bash", "scripts/install-hosts.sh", "--prefix", str(prefix)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Preserving existing unmanaged" in result.stderr
    assert executable.read_text() == "user-owned executable"
    assert not calls.exists()


def test_installer_rejects_release_checksum_mismatch(tmp_path: Path):
    environment, prefix, _ = installer(tmp_path)
    curl = tmp_path / "bin/curl"
    curl.write_text(
        '#!/usr/bin/env python3\nimport pathlib, sys\npathlib.Path(sys.argv[sys.argv.index("--output") + 1]).write_bytes(b"wrong release")\n'
    )
    curl.chmod(0o755)
    result = subprocess.run(
        ["bash", "scripts/install-hosts.sh", "--prefix", str(prefix)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert not (prefix / "bin/autolith").exists()
