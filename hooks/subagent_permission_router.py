#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Permission Router - Claude Code Hook

Auto-approves safe operations to reduce permission prompt fatigue:

1. Primary instances: Read, Glob, Grep are always auto-approved (read-only, no side effects).
   Safe bash commands (ls, git log, etc.) are also auto-approved.
2. Subagents: Same as above, plus Agent tool (subagent spawning for research).

Everything else follows normal permission flow — Write, Edit, Bash (non-read-only),
and other tools still require user approval for primary instances.
"""

import json
import sys

# Tools that are always safe — read-only, no side effects
# Auto-approved for BOTH primary instances and subagents
ALWAYS_SAFE_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "WebSearch",
}

# Additional tools safe only for subagents (not primary instances)
SUBAGENT_EXTRA_SAFE_TOOLS = {
    "Agent",      # Subagents can spawn their own subagents for research
}

# Read-only bash command prefixes safe for auto-approval
SAFE_BASH_PREFIXES = [
    "git log",
    "git diff",
    "git show",
    "git blame",
    "git branch",
    "git status",
    "git rev-parse",
    "git worktree list",
    "git merge-base",
    "git rev-list",
    "git remote",
    "git tag",
    "ls ",
    "ls\n",
    "wc ",
    "file ",
    "which ",
    "command -v",
    "test ",
    "[ ",
    "head ",
    "tail ",
    "cat ",
    "find ",
    "basename ",
    "dirname ",
    "realpath ",
    "date",
    "echo ",
    "printf ",
    "stat ",
    "du ",
    "df ",
    "pwd",
    "whoami",
    "uname",
    "env ",
    "printenv",
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
    """Check if a bash command is read-only and safe for auto-approval."""
    command = command.strip()
    return any(command.startswith(prefix) for prefix in SAFE_BASH_PREFIXES)


def main():
    try:
        input_data = json.load(sys.stdin)

        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        is_subagent = input_data.get("is_subagent", False)

        # Always-safe tools — auto-approve for everyone
        if tool_name in ALWAYS_SAFE_TOOLS:
            context = "subagent" if is_subagent else "primary"
            allow(f"Read-only tool '{tool_name}' auto-approved ({context})")

        # Subagent-only extra safe tools
        if is_subagent and tool_name in SUBAGENT_EXTRA_SAFE_TOOLS:
            allow(f"Safe tool '{tool_name}' auto-approved for subagent")

        # Safe bash commands — auto-approve for everyone
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            if is_safe_bash_command(command):
                context = "subagent" if is_subagent else "primary"
                allow(f"Read-only bash command auto-approved ({context})")

        # Everything else — normal permission flow
        passthrough()

    except json.JSONDecodeError:
        passthrough()
    except Exception:
        # Don't block on hook errors
        passthrough()


if __name__ == "__main__":
    main()
