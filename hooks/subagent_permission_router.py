#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Subagent Permission Router - Claude Code Hook

Auto-approves safe read-only operations for subagents so they don't get
blocked on routine permissions. Primary instances use normal interactive
permissions since the user is watching.

This runs as a PreToolUse hook. It checks if the current session is a
subagent (via session context) and if the tool being used is read-only.
Safe tools are allowed through; everything else follows normal permission flow.
"""

import json
import sys

# Tools that are always safe for subagents — read-only, no side effects
SAFE_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "Agent",      # Subagents can spawn their own subagents for research
}

# Tools that are conditionally safe (need input inspection)
CONDITIONAL_TOOLS = {
    "Bash",       # Safe if the command is read-only (git log, git diff, etc.)
}

# Read-only bash command prefixes that subagents can safely run
SAFE_BASH_PREFIXES = [
    "git log",
    "git diff",
    "git show",
    "git blame",
    "git branch",
    "git status",
    "git rev-parse",
    "git worktree list",
    "ls ",
    "wc ",
    "file ",
    "which ",
    "command -v",
    "test ",
    "[ ",
]


def allow(reason: str):
    """Output structured JSON to auto-approve the tool call, then exit 0."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


def passthrough():
    """Exit 0 with no output — lets normal permission flow decide."""
    sys.exit(0)


def is_safe_bash_command(command: str) -> bool:
    """Check if a bash command is read-only and safe for subagents."""
    command = command.strip()
    return any(command.startswith(prefix) for prefix in SAFE_BASH_PREFIXES)


def main():
    try:
        input_data = json.load(sys.stdin)

        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Check if this is a subagent context
        is_subagent = input_data.get("is_subagent", False)

        if not is_subagent:
            # Primary instance — let normal permission flow handle it
            passthrough()

        # Subagent with a safe tool — auto-approve
        if tool_name in SAFE_TOOLS:
            allow(f"Safe read-only tool '{tool_name}' auto-approved for subagent")

        # Subagent with a conditionally safe tool
        if tool_name in CONDITIONAL_TOOLS:
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                if is_safe_bash_command(command):
                    allow(f"Safe read-only bash command auto-approved for subagent")

        # Everything else — let normal permission flow decide
        passthrough()

    except json.JSONDecodeError:
        passthrough()
    except Exception:
        # Don't block on hook errors
        passthrough()


if __name__ == "__main__":
    main()
