#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Dangerous Command Blocker - Claude Code Hook
Prevents execution of dangerous commands like rm -rf
"""

import json
import re
import shlex
import sys
import os
from datetime import datetime
from pathlib import Path

# Dangerous command patterns
DANGEROUS_PATTERNS = [
    # Direct rm -rf on critical paths
    r'rm\s+(-[rfRF]+\s+|\s+-[rfRF]+)(/\s*$|/\s+|\s+/\s*$|\s+/\s+)',
    r'rm\s+(-[rfRF]+\s+|\s+-[rfRF]+)(\*|\.\s*$|\.\.\s*$)',
    r'rm\s+(-[rfRF]+\s+|\s+-[rfRF]+)(~|\$HOME|\${HOME})',

    # Recursive + force with wildcards
    r'rm\s+.*-r.*-f.*\*',
    r'rm\s+.*-f.*-r.*\*',

    # Long form options
    r'rm\s+.*(--recursive|--force).*(/\s*$|\*)',

    # Prevent removal of current directory or parent
    r'rm\s+-[rfRF]+\s+\./?(\s|$)',
    r'rm\s+-[rfRF]+\s+\.\./?(\s|$)',
]

# Additional context-aware checks
CRITICAL_PATHS = [
    '/',
    '/etc',
    '/usr',
    '/bin',
    '/sbin',
    '/boot',
    '/dev',
    '/lib',
    '/proc',
    '/sys',
    '/var',
    os.path.expanduser('~'),
]

# Dangerous git patterns
DANGEROUS_GIT_PATTERNS = [
    # Block pushes to main/master (direct push, force push, force-with-lease — all blocked)
    (r'git\s+push\s+.*\b(main|master)\b', "Push to main/master (all pushes to main/master are blocked)"),
    (r'git\s+push\b(?!.*\s)$', "Push to default branch (use explicit branch names to avoid pushing to main)"),

    # Discard all local changes
    (r'git\s+checkout\s+\.(\s|$)', "Discard all uncommitted changes (git checkout .)"),
    (r'git\s+restore\s+\.(\s|$)', "Discard all uncommitted changes (git restore .)"),

    # Hard reset
    (r'git\s+reset\s+--hard', "Hard reset discards all uncommitted changes"),

    # Clean untracked files
    (r'git\s+clean\s+.*-f', "Force clean removes untracked files permanently"),

    # Force delete branches
    (r'git\s+branch\s+-D\s+(main|master)\b', "Force delete main/master branch"),
]

# .env file patterns to protect
ENV_FILE_PATTERNS = [
    r'\b\.env\b(?!\.sample)',  # .env but not .env.sample
    r'cat\s+.*\.env\b(?!\.sample)',  # cat .env
    r'echo\s+.*>\s*\.env\b(?!\.sample)',  # echo > .env
    r'touch\s+.*\.env\b(?!\.sample)',  # touch .env
    r'cp\s+.*\.env\b(?!\.sample)',  # cp .env
    r'mv\s+.*\.env\b(?!\.sample)',  # mv .env
]


def is_dangerous_command(command: str) -> tuple[bool, str]:
    """
    Check if command is dangerous.
    Returns (is_dangerous, reason)
    """
    # Check regex patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, f"Command matches dangerous pattern: {pattern}"

    # Check for rm on critical paths
    if 'rm' in command and '-r' in command:
        # Extract path arguments from the rm command
        # Split on spaces but be aware of quoted strings
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command.split()

        # Find paths in the command (arguments that don't start with -)
        paths_in_cmd = [p for p in parts if p and not p.startswith('-') and p != 'rm']

        for path_arg in paths_in_cmd:
            # Normalize the path for comparison
            normalized = os.path.normpath(os.path.expanduser(path_arg))
            # Make it absolute if it starts with / or ~
            if path_arg.startswith('/') or path_arg.startswith('~'):
                abs_path = normalized
            else:
                # Relative path - resolve it
                abs_path = os.path.normpath(os.path.join(os.getcwd(), normalized))

            for critical_path in CRITICAL_PATHS:
                # Check if the path IS the critical path or is a PARENT of it
                # (e.g., rm -rf / would delete /etc, rm -rf /etc deletes /etc)
                crit_normalized = os.path.normpath(critical_path)
                if abs_path == crit_normalized or crit_normalized.startswith(abs_path + os.sep):
                    return True, f"Recursive removal targeting critical path: {critical_path}"

    # Check for multiple wildcards with force/recursive
    if 'rm' in command and ('*' in command or '?' in command):
        if '-rf' in command or '-fr' in command or ('-r' in command and '-f' in command):
            wildcard_count = command.count('*') + command.count('?')
            if wildcard_count > 1:
                return True, "Multiple wildcards with force/recursive flags"

    return False, ""


def is_env_file_access(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """
    Check if any tool is trying to access .env files containing sensitive data.
    Returns (is_accessing_env, reason)
    """
    if tool_name in ['Read', 'Edit', 'MultiEdit', 'Write']:
        file_path = tool_input.get('file_path', '')
        if '.env' in file_path and not file_path.endswith('.env.sample'):
            return True, f"Attempting to access sensitive .env file: {file_path}"

    elif tool_name == 'Bash':
        command = tool_input.get('command', '')
        for pattern in ENV_FILE_PATTERNS:
            if re.search(pattern, command):
                return True, f"Bash command attempting to access .env file"

    return False, ""


def is_dangerous_git_command(command: str) -> tuple[bool, str]:
    """
    Check if a git command is dangerous.
    Returns (is_dangerous, reason)
    """
    for pattern, reason in DANGEROUS_GIT_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, reason
    return False, ""


def suggest_safer_git_alternative(command: str) -> str:
    """Suggest a safer alternative to a dangerous git command."""
    suggestions = []
    if 'push' in command:
        suggestions.append("• Push to a feature branch instead of main/master")
        suggestions.append("• Create a PR to merge changes into main/master")
    if 'checkout .' in command or 'restore .' in command:
        suggestions.append("• Use 'git stash' to save changes temporarily")
        suggestions.append("• Discard specific files: 'git checkout -- <file>'")
    if 'reset --hard' in command:
        suggestions.append("• Use 'git stash' to save changes before resetting")
        suggestions.append("• Use 'git reset --soft' or 'git reset --mixed' to keep changes staged/unstaged")
    if 'clean' in command:
        suggestions.append("• Use 'git clean -n' first to preview what would be deleted")
        suggestions.append("• Use 'git clean -i' for interactive mode")
    return "\n".join(suggestions) if suggestions else "Consider a less destructive git command"


def suggest_safer_alternative(command: str, is_env_access: bool = False) -> str:
    """Suggest a safer alternative to the dangerous command."""
    suggestions = []

    if is_env_access:
        suggestions.append("• Use .env.sample for template files instead")
        suggestions.append("• Store sensitive data in secure credential management systems")
        suggestions.append("• Access environment variables through proper configuration management")
        return "\n".join(suggestions)

    if 'rm -rf' in command or 'rm -fr' in command:
        suggestions.append("• Use 'rm -r' without -f for important deletions (allows prompting)")
        suggestions.append("• Specify exact paths instead of using wildcards")
        suggestions.append("• Consider using 'trash' command to move to trash instead")
        suggestions.append("• Use 'find' with -delete for more controlled deletion")

    if '*' in command:
        suggestions.append("• List files first with 'ls' before using wildcards")
        suggestions.append("• Use specific file patterns instead of broad wildcards")

    return "\n".join(suggestions) if suggestions else "Consider a more specific, safer command"


def log_blocked_command(session_id: str, command: str, reason: str):
    """Log blocked commands for security audit."""
    try:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        log_dir = Path(project_dir) / ".claude" / "security_logs" / session_id
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "blocked_commands.jsonl"
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "reason": reason,
            "action": "blocked"
        }

        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception:
        # Silently fail logging - don't let it affect the blocking
        pass


def main():
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)

        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        session_id = input_data.get("session_id", "unknown")

        # Check for .env file access
        is_env_blocked, env_reason = is_env_file_access(tool_name, tool_input)
        if is_env_blocked:
            log_blocked_command(session_id, str(tool_input), env_reason)

            error_message = f"""BLOCKED: Access to .env files containing sensitive data is prohibited!

Reason: {env_reason}

Safer alternatives:
{suggest_safer_alternative("", is_env_access=True)}

Please use .env.sample for template files instead."""

            print(error_message, file=sys.stderr)
            sys.exit(2)  # Block execution and show stderr to Claude

        # Only process Bash tool calls for dangerous commands
        if tool_name != "Bash":
            sys.exit(0)

        # Extract command
        command = tool_input.get("command", "")

        if not command:
            sys.exit(0)

        # Check for dangerous git commands
        is_git_dangerous, git_reason = is_dangerous_git_command(command)
        if is_git_dangerous:
            log_blocked_command(session_id, command, git_reason)

            error_message = f"""BLOCKED: Dangerous git command detected!

Command: {command}
Reason: {git_reason}

This command could cause irreversible data loss or overwrite shared history.

Safer alternatives:
{suggest_safer_git_alternative(command)}

Please reconsider your approach and use a safer command."""

            print(error_message, file=sys.stderr)
            sys.exit(2)

        # Check if command is dangerous
        is_dangerous, reason = is_dangerous_command(command)

        if is_dangerous:
            # Log the blocked command for audit
            log_blocked_command(session_id, command, reason)

            # Provide detailed feedback to Claude
            error_message = f"""BLOCKED: Dangerous command detected!

Command: {command}
Reason: {reason}

This command could cause irreversible data loss or system damage.

Safer alternatives:
{suggest_safer_alternative(command)}

Please reconsider your approach and use a safer command."""

            print(error_message, file=sys.stderr)
            sys.exit(2)  # Block execution and show stderr to Claude

        # Command is safe, allow execution
        sys.exit(0)

    except json.JSONDecodeError as e:
        print(f"Error parsing input: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Don't block on errors, just log
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
