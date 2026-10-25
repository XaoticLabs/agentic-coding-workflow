#!/usr/bin/env python3
"""Resolve the active checkout from hook cwd, including native worktree moves."""

import json
import os
import subprocess
import sys
from pathlib import Path


def project_directory(data: dict) -> str:
    candidate = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    directory = Path(candidate).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("Hook cwd is not a directory")

    def checkout_root(path: Path) -> Path:
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return path
        return Path(result.stdout.strip()) if result.returncode == 0 else path

    root = checkout_root(directory)
    # A consuming project can intentionally be a subdirectory of a monorepo.
    # Preserve that scope while cwd stays in the same checkout. A native
    # worktree nested under the launch path has a different Git root.
    launch_path = os.environ.get("CLAUDE_PROJECT_DIR")
    if launch_path:
        launch = Path(launch_path).resolve()
        if directory.is_relative_to(launch) and checkout_root(launch) == root:
            return str(launch)
    return str(root)


if __name__ == "__main__":
    try:
        print(project_directory(json.load(sys.stdin)))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f"Cannot resolve the active checkout: {error}", file=sys.stderr)
        raise SystemExit(1)
