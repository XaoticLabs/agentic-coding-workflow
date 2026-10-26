#!/usr/bin/env python3
"""Execute a project-owned experiment matrix and write JSON and an HTML comparison."""

import argparse
import html
import json
from pathlib import Path
import statistics
import subprocess
import sys
import uuid

from workflow_execution import (
    arguments,
    contained,
    digest,
    positive,
    run_command,
    source_state,
    timestamp,
    write_json,
)


def load_matrix(path: Path, project: Path) -> list[dict]:
    matrix = json.loads(path.read_text())
    if (
        not isinstance(matrix, dict)
        or set(matrix) != {"version", "experiments"}
        or matrix["version"] != 1
    ):
        raise ValueError("matrix must contain version: 1 and experiments")
    experiments = matrix["experiments"]
    if not isinstance(experiments, list) or not experiments:
        raise ValueError("experiments must be a nonempty array")
    names = set()
    for experiment in experiments:
        if not isinstance(experiment, dict) or set(experiment) - {
            "name",
            "criterion",
            "command",
            "cwd",
            "timeout_seconds",
            "runs",
            "expected_exit",
        }:
            raise ValueError("invalid experiment fields")
        name = experiment.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("experiments need unique nonempty names")
        names.add(name)
        if (
            not isinstance(experiment.get("criterion"), str)
            or not experiment["criterion"].strip()
        ):
            raise ValueError("each experiment needs an observable criterion")
        arguments(experiment.get("command"))
        contained(project, experiment.get("cwd", "."))
        positive(experiment.get("timeout_seconds", 60), "timeout_seconds")
        runs = experiment.get("runs", 1)
        if isinstance(runs, bool) or not isinstance(runs, int) or not 1 <= runs <= 50:
            raise ValueError("runs must be an integer from 1 to 50")
        if type(experiment.get("expected_exit", 0)) is not int:
            raise ValueError("expected_exit must be an integer")
    return experiments


def render(report: dict) -> str:
    rows = []
    for experiment in report["experiments"]:
        trials = experiment["trials"]
        durations = [trial["duration_seconds"] for trial in trials]
        links = " ".join(
            f'<a href="{html.escape(Path(trial["stdout"]).name, quote=True)}">run {index + 1}</a>'
            for index, trial in enumerate(trials)
        )
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(value))}</td>"
                for value in (
                    experiment["name"],
                    experiment["criterion"],
                    experiment["outcome"],
                    len(trials),
                    f"{statistics.median(durations):.4f}",
                )
            )
            + f"<td>{links}</td></tr>"
        )
    return (
        '<!doctype html><meta charset="utf-8"><title>Experiment comparison</title><style>body{font:16px system-ui;max-width:1100px;margin:3rem auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.7rem;text-align:left}input{padding:.5rem}</style>'
        + (
            '<h1>Experiment comparison</h1><p>Filter and compare observed results. Duration alone does not establish correctness or a speedup.</p><input id="filter" placeholder="Filter experiments" aria-label="Filter experiments">'
            "<table><thead><tr><th>Experiment</th><th>Criterion</th><th>Outcome</th><th>Trials</th><th>Median seconds</th><th>Output</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
            '<p><a href="results.json">Source, commands, raw exits and complete results</a></p><script>document.querySelector("#filter").addEventListener("input",e=>{for(const row of document.querySelectorAll("tbody tr"))row.hidden=!row.textContent.toLowerCase().includes(e.target.value.toLowerCase())})</script>'
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        project = args.project_dir.resolve()
        experiments = load_matrix(args.matrix, project)
        before = source_state(project)
        output = (
            args.output_dir or project / ".claude/experiments" / uuid.uuid4().hex
        ).resolve()
        output.mkdir(parents=True, exist_ok=False)
        report = {
            "status": "RUNNING",
            "candidate": before,
            "matrix_sha256": digest(args.matrix),
            "started_at": timestamp(),
            "experiments": [],
        }
        write_json(output / "results.json", report)
        for index, experiment in enumerate(experiments):
            trials = [
                run_command(
                    experiment["command"],
                    contained(project, experiment.get("cwd", ".")),
                    output / f"experiment-{index}-run-{trial}.log",
                    experiment.get("timeout_seconds", 60),
                    expected_exit=experiment.get("expected_exit", 0),
                )
                for trial in range(experiment.get("runs", 1))
            ]
            report["experiments"].append(
                {
                    **experiment,
                    "trials": trials,
                    "outcome": "passed"
                    if all(trial["outcome"] == "passed" for trial in trials)
                    else "failed",
                }
            )
            write_json(output / "results.json", report)
        report["status"] = (
            "PASSED"
            if all(
                experiment["outcome"] == "passed"
                for experiment in report["experiments"]
            )
            else "FAILED"
        )
        report["after"] = source_state(project)
        report["source_changed"] = report["after"] != before
        # Experiments may deliberately mutate candidates, but cannot claim a fixed-source comparison.
        report["matrix_changed"] = digest(args.matrix) != report["matrix_sha256"]
        report["comparison_valid"] = (
            not report["source_changed"] and not report["matrix_changed"]
        )
        report["finished_at"] = timestamp()
        write_json(output / "results.json", report)
        (output / "comparison.html").write_text(render(report))
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "comparison_valid": report["comparison_valid"],
                    "report": str(output / "comparison.html"),
                }
            )
        )
        return 0 if report["status"] == "PASSED" and report["comparison_valid"] else 1
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        print(f"Experiment error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
