#!/bin/bash
# PostToolUse hook: Auto-commit WIP snapshots after file modifications
# Prevents lost progress by creating lightweight commits with a cooldown
# to avoid noise from rapid successive edits.
#
# Fires on: Edit, Write, NotebookEdit
# Cooldown: 60 seconds between auto-commits
# Skips: subagents, non-git dirs, no changes, plugin repo itself, main/master branches

# Read hook input from stdin — gracefully handle missing/malformed input
input=$(cat 2>/dev/null || echo '{}')

# Only fire on file-modification tools
tool_name=$(echo "$input" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
case "$tool_name" in
    Edit|Write|NotebookEdit) ;;
    *) exit 0 ;;
esac

# Skip subagent sessions (they shouldn't commit)
is_subagent=$(echo "$input" | jq -r '.is_subagent // false' 2>/dev/null || echo "false")
if [ "$is_subagent" = "true" ]; then
    exit 0
fi

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

# Must be a git repo
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# NEVER auto-commit on main or master
current_branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
case "$current_branch" in
    main|master|develop|release|release/*) exit 0 ;;
esac

# Don't auto-commit inside the plugin repo itself
plugin_root="${CLAUDE_PLUGIN_ROOT:-}"
if [ -n "$plugin_root" ] && [ "$CLAUDE_PROJECT_DIR" = "$plugin_root" ]; then
    exit 0
fi

# Cooldown: skip if last auto-commit was < 60 seconds ago
COOLDOWN_FILE="${CLAUDE_PROJECT_DIR}/.claude/.auto-commit-last"
mkdir -p "${CLAUDE_PROJECT_DIR}/.claude"
COOLDOWN_SECONDS=60

if [ -f "$COOLDOWN_FILE" ]; then
    last_commit=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo "0")
    now=$(date +%s)
    elapsed=$((now - last_commit))
    if [ "$elapsed" -lt "$COOLDOWN_SECONDS" ]; then
        exit 0
    fi
fi

# Check if there are any uncommitted changes (staged or unstaged)
if git diff --quiet HEAD 2>/dev/null && git diff --cached --quiet 2>/dev/null; then
    # Check for untracked files too
    untracked=$(git ls-files --others --exclude-standard 2>/dev/null)
    if [ -z "$untracked" ]; then
        exit 0
    fi
fi

# Build a short summary of what changed
changed_summary=$(git diff --stat HEAD 2>/dev/null | tail -1 || echo "")
untracked_count=$(git ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ')

msg="wip: auto-save $(date +%H:%M:%S)"
if [ -n "$changed_summary" ]; then
    msg="$msg — $changed_summary"
fi
if [ "$untracked_count" -gt 0 ]; then
    msg="$msg (+${untracked_count} new)"
fi

# Stage everything (respecting .gitignore) and commit
# Exclude .env files from staging
git add -A 2>/dev/null || exit 0
git reset -- '*.env' '.env*' 2>/dev/null || true
git commit -m "$msg" --no-verify 2>/dev/null || exit 0

# Update cooldown timestamp
date +%s > "$COOLDOWN_FILE"

# Silent success — don't pollute Claude's output
exit 0
