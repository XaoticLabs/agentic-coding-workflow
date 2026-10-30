"""Maak installation verifies downloads and preserves unrelated executables."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def installation(tmp_path: Path):
    root = tmp_path / "checkout"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/install-maak.sh", scripts / "install-maak.sh")
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "scripts/maak").write_text(
        '#!/usr/bin/env bash\nprintf "fixture maak:"\nprintf " <%s>" "$@"\nprintf "\\n"\n'
    )
    archive = tmp_path / "maak.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(source, arcname="maak")
    lock = json.loads((ROOT / "scripts/maak.lock.json").read_text())
    lock["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (scripts / "maak.lock.json").write_text(json.dumps(lock))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    curl = binaries / "curl"
    curl.write_text(
        '#!/usr/bin/env python3\nimport os, pathlib, shutil, sys\n'
        'pathlib.Path(os.environ["DOWNLOAD_RECORD"]).write_text("downloaded")\n'
        'shutil.copyfile(os.environ["MAAK_ARCHIVE"], sys.argv[sys.argv.index("--output") + 1])\n'
    )
    curl.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "MAAK_ARCHIVE": str(archive),
        "DOWNLOAD_RECORD": str(tmp_path / "downloaded"),
    }
    return root, tmp_path / "prefix with spaces", environment


def install(installation):
    root, prefix, environment = installation
    return subprocess.run(
        ["bash", "scripts/install-maak.sh", "--prefix", str(prefix)],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_verified_installation_handles_spaces_and_reuses_the_pinned_release(installation):
    _, prefix, environment = installation
    result = install(installation)
    assert result.returncode == 0, result.stderr
    launcher = prefix / "bin/maak"
    forwarded = subprocess.run(
        [str(launcher), "--file", "path with spaces.scm", "check"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert forwarded.returncode == 0, forwarded.stderr
    assert "<--file> <path with spaces.scm> <check>" in forwarded.stdout
    Path(environment["DOWNLOAD_RECORD"]).unlink()
    assert install(installation).returncode == 0
    assert not Path(environment["DOWNLOAD_RECORD"]).exists()


def test_installer_preserves_unmanaged_executable_before_downloading(installation):
    _, prefix, environment = installation
    (prefix / "bin").mkdir(parents=True)
    launcher = prefix / "bin/maak"
    launcher.write_text("user-owned executable")
    result = install(installation)
    assert result.returncode != 0
    assert "Preserving existing unmanaged" in result.stderr
    assert launcher.read_text() == "user-owned executable"
    assert not Path(environment["DOWNLOAD_RECORD"]).exists()


def test_installer_rejects_checksum_mismatch_without_installing(installation):
    root, prefix, _ = installation
    pin = root / "scripts/maak.lock.json"
    lock = json.loads(pin.read_text())
    lock["sha256"] = "0" * 64
    pin.write_text(json.dumps(lock))
    result = install(installation)
    assert result.returncode != 0
    assert "Maak checksum mismatch" in result.stderr
    assert not (prefix / "bin/maak").exists()
