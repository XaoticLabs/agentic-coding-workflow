#!/usr/bin/env python3
"""Create and discover improvement notebooks without executing experiments."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

PLUGIN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLUGIN / "scripts"))
from workflow_execution import source_state, timestamp, write_json  # noqa: E402

STAGES = {"prepare", "baseline", "candidate", "compare", "decide", "complete"}


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError("experiment ID must use lowercase words separated by hyphens")
    return value


def project_root(path: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"Cannot locate Git project at {path}: {error.stderr.strip()}"
        ) from error
    return Path(result.stdout.strip()).resolve()


def inside(project: Path, path: Path) -> Path:
    if not path.resolve().is_relative_to(project):
        raise ValueError(f"notebook path must stay inside the project: {path}")
    return path


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def read_record(path: Path) -> dict:
    record = read_json(path)
    if (
        type(record.get("version")) is not int
        or record["version"] != 1
        or record.get("id") != path.parent.name
        or record.get("stage") not in STAGES
        or not isinstance(record.get("next_action"), str)
        or not record["next_action"].strip()
    ):
        raise ValueError(
            f"invalid notebook identity, version, stage, or next_action: {path}"
        )
    return record


def summary(path: Path, record: dict) -> dict:
    return {
        "id": record["id"],
        "idea": record.get("idea"),
        "stage": record["stage"],
        "next_action": record["next_action"],
        "record": str(path),
        "report": str(path.with_name("report.md")),
        "baseline": record.get("baseline"),
    }


def start(project: Path, directory: Path, name: str, idea: str) -> dict:
    name = identifier(name)
    if not idea.strip():
        raise ValueError("idea must not be empty")
    path = inside(project, directory / name / "experiment.json")
    if path.exists():
        return {"created": False, **summary(path, read_record(path))}

    # Read everything before creating a notebook; errors must not leave a partial draft.
    record = read_json(Path(__file__).resolve().parents[1] / "assets/experiment.json")
    report = (Path(__file__).resolve().parents[1] / "assets/report.md").read_text()
    accepted_path = inside(project, directory / "baseline.json")
    accepted = read_json(accepted_path) if accepted_path.exists() else None
    if accepted is not None:
        identifier(accepted.get("experiment", ""))
        source = accepted.get("source")
        if not isinstance(source, dict) or not all(
            isinstance(source.get(key), str) and source[key].strip()
            for key in ("revision", "worktree_sha256", "scope")
        ):
            raise ValueError(
                f"accepted baseline needs a source fingerprint: {accepted_path}"
            )
    current = source_state(project)
    record.update(
        id=name,
        idea=idea,
        created_at=timestamp(),
        updated_at=timestamp(),
        starting_source=current,
        baseline={
            "source": accepted["source"] if accepted else current,
            "accepted_experiment": accepted["experiment"] if accepted else None,
        },
    )
    path.parent.mkdir(parents=True, exist_ok=False)
    write_json(path, record)
    path.with_name("report.md").write_text(report.replace("<idea>", idea, 1))
    return {"created": True, **summary(path, record)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser(
        "start", help="create a draft or preserve an existing notebook"
    )
    create.add_argument("id")
    create.add_argument("--idea", required=True)
    status = subparsers.add_parser("status", help="read saved stages and next actions")
    status.add_argument("id", nargs="?")
    for command in (create, status):
        command.add_argument("--project-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        project = project_root(args.project_dir)
        directory = inside(project, project / ".claude/improvements")
        if args.action == "start":
            result = start(project, directory, args.id, args.idea)
        else:
            paths = (
                [directory / identifier(args.id) / "experiment.json"]
                if args.id
                else sorted(directory.glob("*/experiment.json"))
            )
            records = [
                summary(inside(project, path), read_record(path)) for path in paths
            ]
            result = {
                "experiments": records,
                "next_action": "Resume a named experiment, or start an improvement idea."
                if records
                else "No experiments yet. Start with an improvement idea.",
            }
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        print(f"Notebook error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
