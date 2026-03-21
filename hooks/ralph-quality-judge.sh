#!/bin/bash
# Stop hook: LLM-as-judge quality review for Ralph iterations
# Evaluates the committed diff against project conventions before allowing exit.
# Only active in Ralph mode (RALPH_MODE=1).
# Blocks if the judge finds substantive quality issues worth fixing this iteration.

input=$(cat)

# Prevent infinite loops
stop_hook_active=$(echo "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)
if [ "$stop_hook_active" = "true" ]; then
  exit 0
fi

# Only active in Ralph mode
if [ "${RALPH_MODE}" != "1" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR" || exit 0

# Get the diff from the last 2 commits (task commit + plan update commit)
DIFF=$(git diff HEAD~2..HEAD 2>/dev/null)
if [ -z "$DIFF" ]; then
  # No commits to review
  exit 0
fi

# Cap diff size to avoid blowing context — only review first 4000 chars
DIFF_TRIMMED=$(echo "$DIFF" | head -c 4000)

# Read AGENTS.md for project conventions if available
CONVENTIONS=""
if [ -f ".claude/AGENTS.md" ]; then
  CONVENTIONS=$(head -100 ".claude/AGENTS.md")
fi

# Build the judge prompt
JUDGE_PROMPT="You are a code quality judge for an autonomous coding loop. Review this diff and decide if it has substantive quality issues that should be fixed NOW (before moving to the next task).

IMPORTANT: You are reviewing autonomous agent output. Be pragmatic, not pedantic.

BLOCK only for:
- Obvious bugs (nil/null derefs, wrong variable, broken logic)
- Security issues (hardcoded secrets, SQL injection, XSS)
- Violations of project conventions that will cascade (wrong patterns that future tasks will copy)
- Missing error handling on external calls that will crash at runtime

DO NOT BLOCK for:
- Style preferences (naming, formatting — lint handles this)
- Missing tests (the test runner hook handles this)
- Minor inefficiencies that don't affect correctness
- Things that look unusual but actually work

Project conventions:
${CONVENTIONS}

Diff to review:
\`\`\`
${DIFF_TRIMMED}
\`\`\`

Respond with EXACTLY one line — either:
PASS
or:
FAIL: <one-sentence description of the issue that must be fixed>

Nothing else."

# Run the judge
VERDICT=$(echo "$JUDGE_PROMPT" | claude -p --model haiku --output-format text 2>/dev/null | tail -1)

if echo "$VERDICT" | grep -q "^FAIL:"; then
  REASON=$(echo "$VERDICT" | sed 's/^FAIL: //')
  echo "{\"decision\": \"block\", \"reason\": \"Quality review: ${REASON}\"}"
  exit 0
fi

# Pass or unparseable response — allow
exit 0
