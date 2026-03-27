#!/bin/bash
# Stop hook: Ralph mode gates (plan enforcement + quality judge)
# Only active when RALPH_MODE=1.
# Gate 1: Blocks if code changed but IMPLEMENTATION_PLAN.md wasn't updated
# Gate 2: LLM-as-judge review of committed diff for substantive issues

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/lib/common.sh"

input=$(read_hook_input)
check_stop_hook_active "$input" && exit 0
check_ralph_mode || exit 0
cd_project

# ── Gate 1: Plan update enforcement ──────────────────────────────────

plan_file=""
for candidate in IMPLEMENTATION_PLAN.md .claude/plans/IMPLEMENTATION_PLAN.md; do
  if [ -f "$candidate" ]; then
    plan_file="$candidate"
    break
  fi
done

if [ -n "$plan_file" ]; then
  plan_changed=$(git diff --name-only -- "$plan_file" 2>/dev/null; git diff --cached --name-only -- "$plan_file" 2>/dev/null)
  code_changes=$(git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null)

  if [ -z "$plan_changed" ] && [ -n "$code_changes" ]; then
    echo '{"decision": "block", "reason": "Ralph mode: IMPLEMENTATION_PLAN.md was not updated. Mark the completed task as done and add any learnings before exiting."}'
    exit 0
  fi
fi

# ── Gate 2: Quality judge ────────────────────────────────────────────

DIFF=$(git diff HEAD~2..HEAD 2>/dev/null)
if [ -z "$DIFF" ]; then
  exit 0
fi

# Cap diff size to conserve context
DIFF_TRIMMED=$(echo "$DIFF" | head -c 4000)

CONVENTIONS=""
if [ -f ".claude/AGENTS.md" ]; then
  CONVENTIONS=$(head -100 ".claude/AGENTS.md")
fi

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

VERDICT=$(echo "$JUDGE_PROMPT" | claude -p --model haiku --output-format text 2>/dev/null | tail -1)

if echo "$VERDICT" | grep -q "^FAIL:"; then
  REASON=$(echo "$VERDICT" | sed 's/^FAIL: //')
  echo "{\"decision\": \"block\", \"reason\": \"Quality review: ${REASON}\"}"
  exit 0
fi

exit 0
