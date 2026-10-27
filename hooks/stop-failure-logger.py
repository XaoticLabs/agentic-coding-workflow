#!/usr/bin/env python3
"""Observe StopFailure; its output cannot resume or pause the failed turn."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workflow_notifications import notify  # noqa: E402

MESSAGES = {
    "rate_limit": "Rate limit reached.",
    "overloaded": "API overloaded.",
    "authentication_failed": "Authentication failed. Check credentials.",
    "oauth_org_not_allowed": "OAuth organization is not allowed.",
    "account_on_hold": "Account is on hold.",
    "billing_error": "Billing error. Check account.",
    "invalid_request": "API request was invalid.",
    "model_not_found": "Requested model was not found.",
    "server_error": "API server error.",
    "max_output_tokens": "Maximum output tokens reached.",
    "cloud_credential_error": "Cloud credentials failed.",
}


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
        notify(
            "Claude API Failure", MESSAGES.get(data.get("error"), "Unknown API error.")
        )
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        pass  # Observability failures must not break a session.
    return 0


if __name__ == "__main__":
    sys.exit(main())
