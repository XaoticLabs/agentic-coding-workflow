#!/usr/bin/env python3
"""Identify exactly which commit and working files a verification checked."""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(
        ["git", *args], env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    )


def is_runtime(path: str) -> bool:
    return (
        path.startswith(".claude/")
        and not path.startswith(".claude/rules/")
        and path not in (".claude/AGENTS.md", ".claude/project-commands.json")
    )


def snapshot() -> dict:
    revision = git_bytes("rev-parse", "--verify", "HEAD").decode().strip()
    tracked = set(git_bytes("ls-files", "-z").split(b"\0")) - {b""}
    untracked = set(
        git_bytes("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    ) - {b""}
    files = sorted(
        path for path in tracked | untracked if not is_runtime(os.fsdecode(path))
    )
    digest = hashlib.sha256()
    for raw in files:
        path = Path(os.fsdecode(raw))
        digest.update(raw + b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0" + os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(str(stat.S_IMODE(path.stat().st_mode)).encode() + b"\0")
            digest.update(path.read_bytes())
        else:
            digest.update(b"missing\0")
        digest.update(b"\0")
    changed = git_bytes("diff", "--name-only", "-z", "HEAD").split(b"\0")
    dirty = any(
        path and not is_runtime(os.fsdecode(path)) for path in changed + list(untracked)
    )
    return {
        "revision": revision,
        "worktree_sha256": digest.hexdigest(),
        "scope": "worktree" if dirty else "revision",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("snapshot", "record"))
    parser.add_argument("values", nargs="*")
    args = parser.parse_args()
    try:
        if args.operation == "snapshot":
            print(json.dumps(snapshot(), sort_keys=True))
        else:
            before, after, status, session = args.values
            directory = Path(".claude/verification")
            directory.mkdir(parents=True, exist_ok=True)
            name = hashlib.sha256(session.encode()).hexdigest()[:20]
            record = {
                "checked": json.loads(before),
                "after": json.loads(after),
                "status": status,
            }
            temporary = directory / f".{name}-{os.getpid()}.tmp"
            temporary.write_text(json.dumps(record, indent=2) + "\n")
            temporary.replace(directory / f"{name}.json")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Verification state unavailable: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
