"""Shared local fixtures for workflow-controller tests."""

from pathlib import Path
import subprocess

EVALUATION = {
    "verdict": "ACCEPT",
    "scores": {
        name: 4
        for name in (
            "spec_fidelity",
            "correctness",
            "integration_quality",
            "code_quality",
            "test_coverage",
            "maintainability",
        )
    },
    "average": 4,
    "criteria_results": [
        {
            "criterion": "Fixture requirement",
            "result": "PASS",
            "notes": "Verified fixture evidence",
        }
    ],
    "issues": [],
    "summary": "Full run report",
    "revise_guidance": "",
    "verification_integrity": {
        "status": "PASS",
        "notes": "Criteria and runnable coverage preserved; no approved expectation changed",
    },
}


def write_executable(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + contents)
    path.chmod(0o755)


def git(project: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(project), *arguments], text=True
    ).strip()
