"""The combined trace survives its inputs and includes every worker run."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def traces(tmp_path: Path) -> Path:
    destination = tmp_path / "run with 'quotes' and spaces"
    shutil.copytree(ROOT / "tests/fixtures/traces", destination)
    return destination


def stitch(traces: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(ROOT / "scripts/stitch-traces.sh"),
            str(traces / "workers"),
            "fixture",
            str(traces / "orchestrator.jsonl"),
            str(traces / "unified-trace.jsonl"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_fixture_preserves_all_sources_runs_and_timestamp_order(traces: Path) -> None:
    original = (traces / "orchestrator.jsonl").read_bytes()
    result = stitch(traces)
    assert result.returncode == 0, result.stderr
    output = traces / "unified-trace.jsonl"
    events = [json.loads(line) for line in output.read_text().splitlines()]
    assert [event["type"] for event in events] == [
        "parallel_start",
        "run_start",
        "verdict",
        "run_start",
        "run_end",
        "parallel_end",
    ]
    assert [event["source"] for event in events] == [
        "orchestrator",
        "wave0-worker-0",
        "wave0-worker-0",
        "wave0-worker-0",
        "wave1-worker-1",
        "orchestrator",
    ]
    assert events[1]["worker_run"] != events[3]["worker_run"]
    assert (traces / "orchestrator.jsonl").read_bytes() == original
    combined = output.read_bytes()
    assert stitch(traces).returncode == 0
    assert output.read_bytes() == combined  # Idempotent, no duplicate combined input.
    shutil.rmtree(traces / "workers")
    assert output.read_bytes() == combined


def test_bad_input_fails_without_replacing_combined_artifact(traces: Path) -> None:
    assert stitch(traces).returncode == 0
    before = (traces / "unified-trace.jsonl").read_bytes()
    bad = traces / "workers/wave0-worker-0/run-one/trace.jsonl"
    bad.write_text(bad.read_text() + "not json\n")
    result = stitch(traces)
    assert result.returncode != 0
    assert "trace.jsonl:3" in result.stderr
    assert (traces / "unified-trace.jsonl").read_bytes() == before
