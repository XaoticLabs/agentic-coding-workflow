#!/usr/bin/env python3
"""Best-effort native desktop notifications. No network destination is configured."""

import os
import shutil
import subprocess


def notify(title: str, message: str) -> None:
    if os.environ.get("WORKFLOW_NOTIFY", "true").lower() == "false":
        return
    if (
        os.environ.get("WORKFLOW_HOST_WORKER") == "1"
        or os.environ.get("RELAY_MODE") == "1"
    ):
        return  # The owning primary session reports readiness, not its workers.
    title = title.replace("\0", "")[:80]
    message = " ".join(message.replace("\0", "").split())[:160]
    if shutil.which("osascript"):
        command = [
            "osascript",
            "-e",
            "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run",
            "--",
            title,
            message,
        ]
    elif shutil.which("notify-send"):
        command = ["notify-send", "--app-name=Agentic Workflow", "--", title, message]
    else:
        return
    try:
        subprocess.run(command, capture_output=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass
