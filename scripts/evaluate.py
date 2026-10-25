#!/usr/bin/env python3
"""Run a read-only evaluator and bind validated evidence to the checked source."""

import argparse
from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from typing import NotRequired, TypedDict, cast

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = (
    "spec_fidelity",
    "correctness",
    "integration_quality",
    "code_quality",
    "test_coverage",
    "maintainability",
)


class Schema(TypedDict):
    type: str
    additionalProperties: NotRequired[bool]
    required: NotRequired[list[str]]
    properties: NotRequired[dict[str, "Schema"]]
    enum: NotRequired[list[str]]
    items: NotRequired["Schema"]
    minItems: NotRequired[int]
    minLength: NotRequired[int]
    minimum: NotRequired[float]
    maximum: NotRequired[float]


class Criterion(TypedDict):
    criterion: str
    result: str
    notes: str


class Issue(TypedDict):
    dimension: str
    severity: str
    file: str
    line: int
    description: str


class Integrity(TypedDict):
    status: str
    notes: str


class Evaluation(TypedDict):
    verdict: str
    scores: dict[str, float]
    average: float
    criteria_results: list[Criterion]
    issues: list[Issue]
    summary: str
    revise_guidance: str
    verification_integrity: Integrity


class EvaluationArguments(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.base: str = "HEAD"
        self.revision: str = ""
        self.verdict: Path = Path("verdict.json")
        self.summary: Path | None = None
        self.log: Path | None = None
        self.timeout: float = 600
        self.skip: str | None = None


SCHEMA: Schema = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "verdict",
        "scores",
        "average",
        "criteria_results",
        "issues",
        "summary",
        "revise_guidance",
        "verification_integrity",
    ],
    "properties": {
        "verdict": {"type": "string", "enum": ["ACCEPT", "REVISE"]},
        "scores": {
            "type": "object",
            "additionalProperties": False,
            "required": list(DIMENSIONS),
            "properties": {
                name: {"type": "number", "minimum": 1, "maximum": 5}
                for name in DIMENSIONS
            },
        },
        "average": {"type": "number", "minimum": 1, "maximum": 5},
        "criteria_results": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["criterion", "result", "notes"],
                "properties": {
                    "criterion": {"type": "string", "minLength": 1},
                    "result": {"type": "string", "enum": ["PASS", "FAIL", "PARTIAL"]},
                    "notes": {"type": "string", "minLength": 1},
                },
            },
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "severity", "file", "line", "description"],
                "properties": {
                    "dimension": {"type": "string", "enum": list(DIMENSIONS)},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "major", "minor"],
                    },
                    "file": {"type": "string", "minLength": 1},
                    "line": {"type": "integer", "minimum": 1},
                    "description": {"type": "string", "minLength": 1},
                },
            },
        },
        "summary": {"type": "string", "minLength": 1},
        "revise_guidance": {"type": "string"},
        "verification_integrity": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "notes"],
            "properties": {
                "status": {"type": "string", "enum": ["PASS", "FAIL"]},
                "notes": {"type": "string", "minLength": 1},
            },
        },
    },
}


def validate(value: object, schema: Schema = SCHEMA, path: str = "verdict") -> None:
    """Validate this fixed schema locally, independently of CLI enforcement."""
    kind = schema["type"]
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported value")
    if kind == "object" and isinstance(value, dict) and "properties" in schema:
        fields = cast(dict[str, object], value)
        if set(fields) != set(schema.get("required", [])):
            raise ValueError(f"{path}: missing or unknown fields")
        for name, item in fields.items():
            validate(item, schema["properties"][name], f"{path}.{name}")
    elif kind == "array" and isinstance(value, list) and "items" in schema:
        items = cast(list[object], value)
        if len(items) < schema.get("minItems", 0):
            raise ValueError(f"{path}: required evidence is missing")
        for item in items:
            validate(item, schema["items"], path + "[]")
    elif kind == "string" and isinstance(value, str):
        if len(value.strip()) < schema.get("minLength", 0):
            raise ValueError(f"{path}: empty evidence")
    elif (
        kind in ("number", "integer")
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        if kind == "integer" and not isinstance(value, int):
            raise ValueError(f"{path}: expected integer")
        if not math.isfinite(value) or not schema.get(
            "minimum", -math.inf
        ) <= value <= schema.get("maximum", math.inf):
            raise ValueError(f"{path}: out of range")
    else:
        raise ValueError(f"{path}: expected {kind}")


def validate_verdict(value: object) -> Evaluation:
    validate(value)
    payload = cast(Evaluation, value)
    average = sum(payload["scores"].values()) / len(DIMENSIONS)
    if abs(payload["average"] - average) > 0.011:
        raise ValueError("average does not match dimension scores")
    must_revise = (
        min(payload["scores"].values()) < 3
        or average < 3
        or any(item["result"] != "PASS" for item in payload["criteria_results"])
        or any(item["severity"] == "critical" for item in payload["issues"])
        or payload["verification_integrity"]["status"] != "PASS"
    )
    if payload["verdict"] == "ACCEPT" and must_revise:
        raise ValueError("ACCEPT contradicts the evaluation evidence")
    if payload["verdict"] == "REVISE" and not payload["revise_guidance"].strip():
        raise ValueError("REVISE requires actionable guidance")
    return payload


def snapshot() -> dict[str, object]:
    raw = cast(
        object,
        json.loads(
            subprocess.check_output(
                [sys.executable, str(ROOT / "hooks/verification-state.py"), "snapshot"],
                text=True,
            )
        ),
    )
    if not isinstance(raw, dict):
        raise ValueError("invalid candidate state")
    return cast(dict[str, object], raw)


def atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            _ = stream.write(contents)
        _ = temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ui_fingerprint(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("UI evidence must not contain symbolic links")
        if path.is_file():
            digest.update(str(path.relative_to(directory)).encode() + b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def report(result: Mapping[str, object]) -> str:
    if result["verdict"] in ("ERROR", "NOT_RUN"):
        return f"Evaluation: {result['verdict']}\n\n{result['reason']}\n"
    payload = cast(Evaluation, result)
    lines = [
        f"Evaluation: {result['verdict']}",
        f"Revision: {result['revision']}",
        "",
        payload["summary"],
        "",
    ]
    lines.extend(f"- {name}: {score}/5" for name, score in payload["scores"].items())
    lines.extend(
        f"- {item['result']}: {item['criterion']} — {item['notes']}"
        for item in payload["criteria_results"]
    )
    integrity = payload["verification_integrity"]
    lines.append(
        f"- Verification integrity: {integrity['status']} — {integrity['notes']}"
    )
    lines.extend(
        f"- {item['severity']}: {item['file']}:{item['line']}: {item['description']}"
        for item in payload["issues"]
    )
    if payload["revise_guidance"]:
        lines.extend(["", payload["revise_guidance"]])
    return "\n".join(lines) + "\n"


def prepare_evidence(log: Path, base: str, revision: str) -> list[str]:
    log.parent.mkdir(parents=True, exist_ok=True)
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", base, revision, "--"],
        text=True,
    ).split("\0")
    changed += subprocess.check_output(
        ["git", "log", "--format=", "--name-only", "-z", f"{base}..{revision}", "--"],
        text=True,
    ).split("\0")
    if any(protected_path(Path(name)) for name in changed if name):
        raise ValueError(
            "Changes include protected secret paths; separate review is required"
        )
    evidence: list[str] = []
    for suffix, command in (
        (
            "diff",
            [
                "git",
                "--no-pager",
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                base,
                revision,
                "--",
            ],
        ),
        (
            "commits",
            [
                "git",
                "--no-pager",
                "log",
                "--oneline",
                f"{base}..{revision}",
                "--",
            ],
        ),
        # Include intermediate test edits even when the final diff hides a new
        # test that was weakened later in the same iteration. No RED marker is
        # required, and additions in an existing file are ordinary review data.
        (
            "history",
            [
                "git",
                "--no-pager",
                "log",
                "--reverse",
                "--format=fuller",
                "--no-ext-diff",
                "--no-textconv",
                "-p",
                f"{base}..{revision}",
                "--",
            ],
        ),
    ):
        path = log.with_name(log.name + "." + suffix)
        with path.open("w") as stream:
            _ = subprocess.run(command, stdout=stream, check=True)
        evidence.append(str(path.resolve()))
    return evidence


def protected_path(path: Path) -> bool:
    # Do not let the controller's generated diff bypass native Read denies.
    return any(
        part in (".env", ".aws", ".ssh", "secrets") or part.startswith(".env.")
        for part in path.parts
    )


def read_ui_evidence() -> tuple[Path | None, str | None]:
    ui_evidence = os.environ.get("RALPH_EVAL_UI_EVIDENCE", "")
    ui = None
    ui_hash = None
    if os.environ.get("RALPH_EVALUATE_UI", "false") == "true":
        ui = Path(ui_evidence).resolve()
        if (
            not ui_evidence
            or not ui.is_dir()
            or not ui.is_relative_to(Path.cwd())
            or not any(ui.iterdir())
        ):
            raise ValueError(
                "UI evaluation requires pre-recorded RALPH_EVAL_UI_EVIDENCE inside the project"
            )
        ui_hash = ui_fingerprint(ui)
    return ui, ui_hash


CLAUDE_EVALUATOR = [
    "claude",
    "-p",
    "--restricted",
    "--permission-mode",
    "dontAsk",
    "--tools",
    "Read,Glob,Grep",
    "--allowedTools",
    "Read,Glob,Grep",
    "--disallowedTools",
    "Bash",
    "Write",
    "Edit",
    "NotebookEdit",
    "mcp__*",
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers":{}}',
    "--settings",
    json.dumps(
        {
            "disableAllHooks": True,
            "permissions": {
                "deny": [
                    "Read(.env)",
                    "Read(.env.*)",
                    "Read(.aws/**)",
                    "Read(.ssh/**)",
                    "Read(secrets/**)",
                ]
            },
        }
    ),
    "--model",
    "sonnet",
    "--output-format",
    "json",
    "--json-schema",
    json.dumps(SCHEMA),
]


def run_evaluator_cli(prompt: str, log: Path, budget: float) -> Evaluation:
    with (
        log.open("w") as output,
        Path(str(log) + ".stderr.log").open("w") as errors,
    ):
        process = subprocess.Popen(
            CLAUDE_EVALUATOR,
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=errors,
            text=True,
            start_new_session=True,
        )
        try:
            _ = process.communicate(prompt, timeout=budget)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                _ = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                _ = process.communicate()
            raise ValueError("evaluator timed out") from None
    if process.returncode != 0:
        raise ValueError(f"evaluator exited {process.returncode}; see {log}.stderr.log")
    envelope = cast(object, json.loads(log.read_text()))
    if not isinstance(envelope, dict):
        raise ValueError("evaluator did not return a CLI result object")
    fields = cast(dict[str, object], envelope)
    if fields.get("is_error") is not False or fields.get("subtype") != "success":
        raise ValueError("evaluator did not return a successful CLI result")
    verdict = validate_verdict(fields.get("structured_output"))
    return verdict


def evaluate(args: EvaluationArguments, prompt: str) -> dict[str, object]:
    if not args.log or args.timeout <= 0:
        raise ValueError("evaluation requires a log and a positive timeout")
    args.base = resolve_commit(args.base)
    args.revision = resolve_commit(args.revision)
    before = snapshot()
    if before["revision"] != args.revision:
        raise ValueError("candidate revision changed before evaluation")
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], text=True
    ).strip():
        raise ValueError("evaluation requires a clean candidate checkout")
    evidence = prepare_evidence(args.log, args.base, args.revision)
    ui, ui_hash = read_ui_evidence()
    if ui is not None:
        evidence.append(str(ui))
    prompt = (
        prompt
        + "\n\nController-provided diff and commit evidence:\n"
        + "\n".join(evidence)
    )
    prompt += "\nReturn the structured verdict. The controller writes reports; you have read-only tools."
    verdict = run_evaluator_cli(prompt, args.log, args.timeout)
    if snapshot() != before or (ui is not None and ui_fingerprint(ui) != ui_hash):
        raise ValueError("candidate changed during evaluation")
    result: dict[str, object] = {
        **verdict,
        "revision": args.revision,
        "base_revision": args.base,
        "checked": before,
    }
    if ui_hash:
        result["ui_evidence_sha256"] = ui_hash
    return result


def resolve_commit(reference: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{reference}^{{commit}}"],
        text=True,
    ).strip()


def parse_arguments() -> EvaluationArguments:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--base", default="HEAD")
    _ = parser.add_argument("--revision", required=True)
    _ = parser.add_argument("--verdict", type=Path, required=True)
    _ = parser.add_argument("--summary", type=Path)
    _ = parser.add_argument("--log", type=Path)
    _ = parser.add_argument("--timeout", type=float, default=600)
    _ = parser.add_argument("--skip")
    return parser.parse_args(namespace=EvaluationArguments())


def main() -> int:
    args = parse_arguments()
    result: dict[str, object] = {
        "verdict": "NOT_RUN",
        "revision": args.revision,
        "base_revision": args.base,
        "reason": args.skip or "evaluation has not completed",
    }
    atomic_write(args.verdict, json.dumps(result, indent=2) + "\n")
    try:
        if not args.skip:
            result = evaluate(args, sys.stdin.read())

    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result = {**result, "verdict": "ERROR", "reason": str(error)}
        print(f"Evaluation error: {error}", file=sys.stderr)
    atomic_write(args.verdict, json.dumps(result, indent=2) + "\n")
    if args.summary:
        atomic_write(args.summary, report(result))
    print(result["verdict"])
    return {"ACCEPT": 0, "REVISE": 1, "ERROR": 3, "NOT_RUN": 0}[
        cast(str, result["verdict"])
    ]


if __name__ == "__main__":
    sys.exit(main())
