#!/usr/bin/env bash
# Ship Gate — PreToolUse hook that blocks `gh pr create` unless:
#   1. .claude/pr-description.md exists (description was generated)
#   2. .claude/pr-description.md contains a marker showing user approved it
#
# Hook protocol: exit 0 = allow, exit 2 + stderr = block with message to Claude

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

# Only gate Bash tool calls containing `gh pr create`
if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

if ! echo "$COMMAND" | grep -q "gh pr create"; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PR_DESC="$PROJECT_DIR/.claude/pr-description.md"

# Gate 1: PR description file must exist
if [ ! -f "$PR_DESC" ]; then
  cat >&2 <<'EOF'
BLOCKED: Cannot run `gh pr create` — .claude/pr-description.md does not exist.

You MUST generate the PR description file BEFORE creating the PR.
Follow the ship skill phases in order: generate description → get user approval → create PR.
EOF
  exit 2
fi

# Gate 2: File must contain the approval marker
if ! grep -q "^<!-- user-approved -->" "$PR_DESC"; then
  cat >&2 <<'EOF'
BLOCKED: Cannot run `gh pr create` — PR description has not been approved by the user.

You MUST:
1. Show the user the contents of .claude/pr-description.md
2. Use AskUserQuestion to get their approval
3. After approval, add the marker "<!-- user-approved -->" to the TOP of .claude/pr-description.md
4. THEN run `gh pr create`

Do NOT skip user review. This is enforced by a hook and cannot be bypassed.
EOF
  exit 2
fi

# Gate 3: PR title must come from --title flag using the first commit message
# Extract the --title value from the command
PR_TITLE=$(echo "$COMMAND" | grep -oP '(?<=--title ")[^"]*' || echo "$COMMAND" | grep -oP "(?<=--title ')[^']*" || echo "")

if [ -z "$PR_TITLE" ]; then
  cat >&2 <<'EOF'
BLOCKED: Cannot run `gh pr create` without an explicit --title flag.

You MUST derive the PR title from the first commit on the branch:
  BASE=$(git merge-base HEAD main || git merge-base HEAD master)
  PR_TITLE=$(git log --oneline --reverse "${BASE}..HEAD" | head -1 | cut -d' ' -f2-)
  gh pr create --title "$PR_TITLE" ...
EOF
  exit 2
fi

# All gates passed
exit 0
