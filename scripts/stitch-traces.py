#!/usr/bin/env python3
"""Atomically combine preserved worker traces and an orchestrator trace."""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def read_events(path: Path, source: str, run: str) -> list[dict]:
    events = []
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict) or not isinstance(event.get("ts"), str):
                    raise ValueError("event must be an object with a ts string")
                # Compare instants, including timestamps carrying different offsets.
                timestamp = datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    raise ValueError("timestamp must include a timezone")
                event["source"] = source
                if run:
                    event["worker_run"] = run
                events.append(event)
            except ValueError as error:
                raise ValueError(f"{path}:{number}: {error}") from error
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_base", type=Path)
    parser.add_argument("slug")
    parser.add_argument("orchestrator_trace", nargs="?", type=Path)
    parser.add_argument("output", nargs="?", type=Path)
    args = parser.parse_args()
    output = args.output or args.artifact_base / "unified-trace.jsonl"
    temporary = None
    try:
        if (
            args.orchestrator_trace
            and output.resolve() == args.orchestrator_trace.resolve()
        ):
            raise ValueError("combined output must differ from the orchestrator trace")
        events = []
        if args.orchestrator_trace:
            events.extend(read_events(args.orchestrator_trace, "orchestrator", ""))
        for path in sorted(args.artifact_base.rglob("*.jsonl")):
            if path.resolve() in (
                output.resolve(),
                args.orchestrator_trace.resolve() if args.orchestrator_trace else None,
            ):
                continue
            if path.name != "trace.jsonl" and not path.name.endswith("-trace.jsonl"):
                continue
            relative = path.relative_to(args.artifact_base)
            if len(relative.parts) < 2:
                continue
            events.extend(read_events(path, relative.parts[0], str(relative.parent)))
        events.sort(
            key=lambda event: datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            for event in events:
                stream.write(json.dumps(event, separators=(",", ":")) + "\n")
        os.replace(temporary, output)
        print(f"Unified trace: {output} ({len(events)} events)")
    except (OSError, ValueError) as error:
        print(f"Trace stitching failed: {error}", file=sys.stderr)
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
