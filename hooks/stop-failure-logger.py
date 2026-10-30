#!/usr/bin/env python3
"""Observe StopFailure; its output cannot resume or pause the failed turn."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

def main() -> int:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return 0
        root = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        directory = Path(root) / ".claude/logs"
        directory.mkdir(parents=True, exist_ok=True)
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": "StopFailure"}
        for field in ("session_id", "error", "error_details", "last_assistant_message"):
            entry[field] = data.get(field, "")
        with (directory / "stop-failures.jsonl").open("a") as stream:
            stream.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except (OSError, ValueError, TypeError):
        pass  # Observability failures must not break a session.
    return 0


if __name__ == "__main__":
    sys.exit(main())
