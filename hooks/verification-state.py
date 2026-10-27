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
from typing import cast


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(
        ["git", *args], env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    )


def is_runtime(path: str) -> bool:
    return (
        path.startswith(".claude/")
        and not path.startswith(".claude/rules/")
        and not path.startswith(".claude/specs/")
        and not path.startswith(".claude/skills/")
        and path
        not in (
            ".claude/AGENTS.md",
            ".claude/project-commands.json",
            ".claude/project-environment.json",
            ".claude/relay-policy.json",
            ".claude/settings.json",
            ".claude/settings.local.json",
        )
    )


def snapshot() -> dict[str, str]:
    revision = git_bytes("rev-parse", "--verify", "HEAD").decode().strip()
    tracked = set(git_bytes("ls-files", "-z").split(b"\0")) - {b""}
    untracked = set(
        git_bytes("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    ) - {b""}
    # Guidance is often ignored by Git but still changes what verification means.
    for directory in (
        Path(".claude/rules"),
        Path(".claude/specs"),
        Path(".claude/skills"),
    ):
        if directory.is_dir():
            untracked.update(
                os.fsencode(path) for path in directory.rglob("*") if path.is_file()
            )
    for name in (
        ".claude/AGENTS.md",
        ".claude/project-commands.json",
        ".claude/project-environment.json",
        ".claude/relay-policy.json",
        ".claude/settings.json",
        ".claude/settings.local.json",
    ):
        if Path(name).is_file():
            untracked.add(os.fsencode(name))
    untracked.difference_update(tracked)
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


def record_path(session: str) -> Path:
    name = hashlib.sha256(session.encode()).hexdigest()[:20]
    return Path(".claude/verification") / f"{name}.json"


def read_record(session: str) -> dict[str, object]:
    try:
        raw = cast(object, json.loads(record_path(session).read_text()))
        return cast(dict[str, object], raw) if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def write_record(session: str, record: dict[str, object]) -> None:
    path = record_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}-{os.getpid()}.tmp")
    _ = temporary.write_text(json.dumps(record, indent=2) + "\n")
    _ = temporary.replace(path)


class StateArguments(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.operation: str = ""
        self.values: list[str] = []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("operation", choices=("snapshot", "record", "attempt"))
    _ = parser.add_argument("values", nargs="*")
    args = parser.parse_args(namespace=StateArguments())
    try:
        if args.operation == "snapshot":
            print(json.dumps(snapshot(), sort_keys=True))
        elif args.operation == "attempt":
            before, session, active = args.values
            state = cast(object, json.loads(before))
            previous = read_record(session) if active == "true" else {}
            if (
                previous.get("status") == "passed"
                and previous.get("checked") == previous.get("after") == state
            ):
                print(json.dumps({"action": "passed"}))
            else:
                attempts = previous.get("attempt", 0)
                if type(attempts) is not int or attempts < 0:
                    attempts = 0
                blocked = attempts >= 3
                write_record(
                    session,
                    {
                        "checked": state,
                        "after": {},
                        "attempt": attempts if blocked else attempts + 1,
                        "status": "blocked" if blocked else "running",
                    },
                )
                print(json.dumps({"action": "blocked" if blocked else "run"}))
        else:
            before, after, status, session = args.values
            record = {
                "checked": cast(object, json.loads(before)),
                "after": cast(object, json.loads(after)),
                "status": status,
                "attempt": read_record(session).get("attempt", 1),
            }
            write_record(session, record)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Verification state unavailable: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
