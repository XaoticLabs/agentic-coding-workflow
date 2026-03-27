#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
PostToolUse Hook: Audit Logger

Logs every tool call to .claude/logs/tool-calls.jsonl for debugging,
token analysis, and session replay. Each line is a self-contained JSON
object with timestamp, tool name, input summary, and session context.

Truncates large inputs (file contents, long commands) to keep logs manageable.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

MAX_INPUT_LENGTH = 500  # Truncate tool_input values longer than this


def truncate_value(value, max_len=MAX_INPUT_LENGTH):
    """Truncate a string value, preserving the start and noting truncation."""
    if not isinstance(value, str):
        value = str(value)
    if len(value) <= max_len:
        return value
    return value[:max_len] + f"... [truncated, {len(value)} chars total]"


def summarize_input(tool_name: str, tool_input: dict) -> dict:
    """Create a concise summary of tool input for logging."""
    summary = {}
    for key, value in tool_input.items():
        if key == "content":
            # File content — just note length
            summary[key] = f"[{len(str(value))} chars]"
        elif key == "command":
            summary[key] = truncate_value(value, 300)
        elif key == "file_path":
            summary[key] = value  # Always keep full path
        elif key == "pattern":
            summary[key] = value  # Always keep search patterns
        elif key == "prompt":
            summary[key] = truncate_value(value, 200)
        elif isinstance(value, str) and len(value) > MAX_INPUT_LENGTH:
            summary[key] = truncate_value(value)
        else:
            summary[key] = value
    return summary


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    session_id = input_data.get("session_id", "unknown")

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    log_dir = Path(project_dir) / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tool-calls.jsonl"

    entry = {
        "ts": datetime.now().isoformat(),
        "session": session_id[:12] if len(session_id) > 12 else session_id,
        "tool": tool_name,
        "input": summarize_input(tool_name, tool_input),
    }

    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception:
        pass  # Never fail on logging

    sys.exit(0)


if __name__ == "__main__":
    main()
