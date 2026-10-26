#!/usr/bin/env python3
"""Opt-in real container proof: setup, concurrent ports, source edits, failure and cleanup."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--engine", choices=("podman", "docker"), default="podman")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".gitignore").write_text(".claude/\n.env\n")
    (project / "source.txt").write_text("baseline")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Smoke",
            "-c",
            "user.email=smoke@localhost",
            "commit",
            "--quiet",
            "-m",
            "baseline",
        ],
    ):
        subprocess.run(command, cwd=project, check=True)
    (project / "source.txt").write_text("current uncommitted edit")
    (project / ".env").write_text("HOST_SECRET_MUST_NOT_BE_EXPORTED=private")
    (project / ".claude/project-commands.json").write_text(
        json.dumps(
            {
                "install": "python3 -c \"from pathlib import Path; Path('installed.txt').write_text('ready')\"",
                "test": "python3 -c \"import urllib.request; from pathlib import Path; assert urllib.request.urlopen('http://127.0.0.1:8080/source.txt').read() == b'current uncommitted edit'; assert Path('installed.txt').read_text() == 'ready'; assert not Path('.env').exists(); Path('candidate.txt').write_text('candidate only'); print('REAL_CONTAINER_FLOW_PASSED')\"",
            }
        )
    )
    recipe = {
        "version": 1,
        "engine": args.engine,
        "image": args.image,
        "timeout_seconds": 60,
        "services": [
            {
                "name": "app",
                "command": ["python3", "-m", "http.server", "8080"],
                "ready": [
                    "python3",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/installed.txt', timeout=2)",
                ],
                "timeout_seconds": 10,
            }
        ],
    }
    recipe_path = project / ".claude/project-environment.json"
    recipe_path.write_text(json.dumps(recipe))

    def run(name):
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/project-environment.py"),
                "--project-dir",
                str(project),
                "--output-dir",
                str(output / name),
                "--actions",
                "install",
                "test",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        (output / f"{name}.stdout").write_text(process.stdout)
        (output / f"{name}.stderr").write_text(process.stderr)
        report = json.loads((output / name / "run.json").read_text())
        return {
            "case": name,
            "exit": process.returncode,
            "status": report["status"],
            "record": str(output / name / "run.json"),
        }

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("concurrent-a", "concurrent-b")))
    assert all(
        result["status"] == "PASSED" and result["exit"] == 0 for result in results
    ), results
    assert not (project / "candidate.txt").exists()
    assert (project / "source.txt").read_text() == "current uncommitted edit"
    assert (output / "concurrent-a/artifacts/candidate.patch").read_text().find(
        "candidate only"
    ) >= 0
    recipe["services"][0]["ready"] = ["python3", "-c", "raise SystemExit(1)"]
    recipe["services"][0]["timeout_seconds"] = 0.5
    recipe_path.write_text(json.dumps(recipe))
    failure = run("readiness-failure")
    assert failure["status"] == "ERROR" and failure["exit"] != 0, failure
    results.append(failure)
    recipe.update(services=[], timeout_seconds=2)
    recipe_path.write_text(json.dumps(recipe))
    commands_path = project / ".claude/project-commands.json"
    commands = json.loads(commands_path.read_text())
    commands["test"] = "python3 -c 'import time; time.sleep(30)'"
    commands_path.write_text(json.dumps(commands))
    timed_out = run("timeout")
    assert timed_out["status"] == "TIMEOUT" and timed_out["exit"] != 0, timed_out
    results.append(timed_out)
    containers = subprocess.check_output(
        [args.engine, "ps", "--all", "--format", "{{.Names}}"], text=True
    )
    for result in results:
        record = json.loads(Path(result["record"]).read_text())
        owned = record["command"][record["command"].index("--name") + 1]
        assert owned not in containers.splitlines(), owned
    (output / "summary.json").write_text(
        json.dumps(
            {
                "status": "PASSED",
                "checks": results,
                "host_source_preserved": True,
                "owned_containers_removed": True,
            },
            indent=2,
        )
        + "\n"
    )
    print(output / "summary.json")


if __name__ == "__main__":
    main()
