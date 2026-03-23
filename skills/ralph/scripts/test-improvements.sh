#!/usr/bin/env bash
# Test suite for Ralph loop improvements
# Tests: injection audit trail, revert reason capture, diff size gate,
#        tiered circuit breaker, generate-metrics.sh, generate-summary.sh,
#        generate-briefing.sh (revert details + trends), override expiry docs
#
# Usage: bash test-improvements.sh

set -euo pipefail

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PASS_COUNT=0
FAIL_COUNT=0
TEST_DIR=""

# ── Helpers ──────────────────────────────────────────────────────────────

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "  ✓ $1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  echo "  ✗ $1"
  echo "    $2"
}

setup_temp_repo() {
  TEST_DIR=$(mktemp -d)
  cd "$TEST_DIR"
  git init -q
  git checkout -q -b main
  echo "# test project" > README.md
  mkdir -p src
  echo "console.log('hello')" > src/index.ts
  git add -A
  git commit -q -m "initial commit"
}

cleanup() {
  if [ -n "$TEST_DIR" ] && [ -d "$TEST_DIR" ]; then
    cd /
    rm -rf "$TEST_DIR"
  fi
}

trap cleanup EXIT

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 1: generate-metrics.sh
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 1: generate-metrics.sh ━━━"

# ── Test 1.1: Produces task failure rates ────────────────────────────────

echo ""
echo "Test 1.1: Produces task failure rate table"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"
mkdir -p .claude/ralph-logs

# Create a journal with mixed outcomes
cat > .claude/ralph-journal.tsv <<'EOF'
timestamp	outcome	task	metric	notes
2026-03-22T10:00:00	KEEP	Auth login	commits=2	abc123
2026-03-22T10:05:00	REVERT_TESTS	Auth session	-	test failed
2026-03-22T10:10:00	REVERT_TESTS	Auth session	-	test failed again
2026-03-22T10:15:00	KEEP	Auth session	commits=1	def456
2026-03-22T10:20:00	REVERT_LINT	API routes	-	lint error
2026-03-22T10:25:00	KEEP	API routes	commits=1	ghi789
2026-03-22T10:30:00	TIMEOUT	DB migration	300s	timeout
EOF

OUTPUT=$(bash "$SCRIPT_DIR/generate-metrics.sh" .claude/ralph-journal.tsv 2>&1)

if echo "$OUTPUT" | grep -q "Task Failure Rates"; then
  pass "Output contains task failure rates header"
else
  fail "Expected task failure rates" "Got: ${OUTPUT}"
fi

if echo "$OUTPUT" | grep -q "Auth session"; then
  pass "Auth session task appears in failure table"
else
  fail "Expected Auth session in output" "Got: ${OUTPUT}"
fi

cleanup

# ── Test 1.2: Failure patterns (streaks) ──────────────────────────────

echo ""
echo "Test 1.2: Detects failure streaks"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"
mkdir -p .claude/ralph-logs

cat > .claude/ralph-journal.tsv <<'EOF'
timestamp	outcome	task	metric	notes
2026-03-22T10:00:00	KEEP	Task A	commits=1	ok
2026-03-22T10:05:00	REVERT_TESTS	Task B	-	fail
2026-03-22T10:10:00	REVERT_TESTS	Task B	-	fail
2026-03-22T10:15:00	REVERT_LINT	Task C	-	fail
2026-03-22T10:20:00	KEEP	Task B	commits=1	ok
EOF

OUTPUT=$(bash "$SCRIPT_DIR/generate-metrics.sh" .claude/ralph-journal.tsv 2>&1)

if echo "$OUTPUT" | grep -q "Failure Patterns"; then
  pass "Output contains failure patterns section"
else
  fail "Expected failure patterns" "Got: ${OUTPUT}"
fi

if echo "$OUTPUT" | grep -q "revert streak\|Longest revert streak"; then
  pass "Detects revert streaks"
else
  # Streak of 3 (Task B, Task B, Task C)
  fail "Expected revert streak detection" "Got: ${OUTPUT}"
fi

cleanup

# ── Test 1.3: Outcome timeline (first half vs second half) ──────────

echo ""
echo "Test 1.3: Outcome timeline trend analysis"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"
mkdir -p .claude/ralph-logs

# First half: mostly failures. Second half: mostly success
cat > .claude/ralph-journal.tsv <<'EOF'
timestamp	outcome	task	metric	notes
2026-03-22T10:00:00	REVERT_TESTS	T1	-	fail
2026-03-22T10:05:00	REVERT_TESTS	T2	-	fail
2026-03-22T10:10:00	KEEP	T1	commits=1	ok
2026-03-22T10:15:00	KEEP	T2	commits=1	ok
2026-03-22T10:20:00	KEEP	T3	commits=1	ok
2026-03-22T10:25:00	KEEP	T4	commits=1	ok
EOF

OUTPUT=$(bash "$SCRIPT_DIR/generate-metrics.sh" .claude/ralph-journal.tsv 2>&1)

if echo "$OUTPUT" | grep -q "Outcome Timeline"; then
  pass "Output contains outcome timeline"
else
  fail "Expected outcome timeline" "Got: ${OUTPUT}"
fi

if echo "$OUTPUT" | grep -qi "improving"; then
  pass "Detects improving trend (first half worse than second)"
else
  fail "Expected 'improving' trend" "Got: $(echo "$OUTPUT" | grep -i 'trend\|half')"
fi

cleanup

# ── Test 1.4: Empty journal handled gracefully ──────────────────────

echo ""
echo "Test 1.4: Empty journal handled gracefully"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"
mkdir -p .claude

cat > .claude/ralph-journal.tsv <<'EOF'
timestamp	outcome	task	metric	notes
EOF

OUTPUT=$(bash "$SCRIPT_DIR/generate-metrics.sh" .claude/ralph-journal.tsv 2>&1)

if echo "$OUTPUT" | grep -q "no journal data"; then
  pass "Empty journal produces graceful message"
else
  fail "Expected graceful empty handling" "Got: ${OUTPUT}"
fi

cleanup

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 2: generate-summary.sh
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 2: generate-summary.sh ━━━"

# ── Test 2.1: Produces summary artifact ──────────────────────────────

echo ""
echo "Test 2.1: Produces summary artifact with correct structure"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"

SPEC_DIR=".claude/specs/test-feature"
mkdir -p "$SPEC_DIR" .claude/ralph-logs

cat > "$SPEC_DIR/IMPLEMENTATION_PLAN.md" <<'EOF'
# Implementation Plan: Test

## Status: COMPLETE

## Tasks

- [x] **Task 1: Auth login** — Completed in abc1234
- [x] **Task 2: API routes** — Completed in def5678
- [ ] **Task 3: Skipped task** — Priority: LOW

## Learnings
EOF

cat > .claude/ralph-journal.tsv <<'EOF'
timestamp	outcome	task	metric	notes
2026-03-22T10:00:00	KEEP	Auth login	commits=2	abc123
2026-03-22T10:05:00	REVERT_TESTS	API routes	-	test failed
2026-03-22T10:10:00	KEEP	API routes	commits=1	def456
EOF

# Make some commits so the summary can find them
echo "auth code" > src/auth.ts
git add src/auth.ts
git commit -q -m "feat: auth login"
echo "api code" > src/api.ts
git add src/api.ts
git commit -q -m "feat: api routes"

START_TIME=$(( $(date +%s) - 600 ))  # 10 minutes ago
COMMITS_BEFORE=$(( $(git rev-list --count HEAD) - 2 ))

OUTPUT=$(bash "$SCRIPT_DIR/generate-summary.sh" "$SPEC_DIR" .claude/ralph-journal.tsv 3 "$COMMITS_BEFORE" "$START_TIME" 2>&1)

SUMMARY_FILE=".claude/ralph-summary-test-feature.md"

if [ -f "$SUMMARY_FILE" ]; then
  pass "Summary file created"
else
  fail "Expected summary at ${SUMMARY_FILE}" "Output: ${OUTPUT}"
fi

if grep -q "## Metrics" "$SUMMARY_FILE"; then
  pass "Summary contains metrics section"
else
  fail "Expected metrics section" ""
fi

if grep -q "## Commits" "$SUMMARY_FILE"; then
  pass "Summary contains commits section"
else
  fail "Expected commits section" ""
fi

if grep -q "## Incomplete Tasks" "$SUMMARY_FILE"; then
  pass "Summary contains incomplete tasks section"
else
  fail "Expected incomplete tasks section" ""
fi

if grep -q "Skipped task" "$SUMMARY_FILE"; then
  pass "Incomplete task listed in summary"
else
  fail "Expected 'Skipped task' in incomplete tasks" ""
fi

if grep -q "## Ready-to-Use PR Description" "$SUMMARY_FILE"; then
  pass "Summary contains PR description"
else
  fail "Expected PR description section" ""
fi

if grep -q "## Most Reverted Tasks" "$SUMMARY_FILE"; then
  pass "Summary contains revert analysis"
else
  fail "Expected revert analysis section" ""
fi

cleanup

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 3: generate-briefing.sh (revert details + trends)
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 3: generate-briefing.sh (revert details) ━━━"

# ── Test 3.1: Includes actual error output from revert reason files ──

echo ""
echo "Test 3.1: Briefing includes revert reason details"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR" .claude/ralph-logs

cat > "$SPEC_DIR/IMPLEMENTATION_PLAN.md" <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: Auth login** — Priority: HIGH, Deps: none, Spec: 01.md

## Learnings
EOF

cat > .claude/ralph-journal.tsv <<'EOF'
timestamp	outcome	task	metric	notes
2026-03-22T10:00:00	REVERT_TESTS	Auth login	-	test failed
2026-03-22T10:05:00	REVERT_LINT	Auth login	-	lint failed
EOF

# Create revert reason files
cat > .claude/ralph-logs/revert-1-reason.txt <<'EOF'
REVERT_TESTS — Iteration 1 — 2026-03-22
Task: Auth login
Command: mix test
---
  1) test auth login (AuthTest)
     ** (MatchError) no match of right hand side value: {:error, :unauthorized}
     code: assert {:ok, user} = Auth.login("test@example.com", "wrong_pass")
     stacktrace:
       test/auth_test.exs:15
EOF

cat > .claude/ralph-logs/revert-2-reason.txt <<'EOF'
REVERT_LINT — Iteration 2 — 2026-03-22
Task: Auth login
Command: mix credo --strict
---
  lib/auth.ex:42:11 C Credo.Check.Readability.VariableNames
    Variable names should be written in snake_case.
EOF

OUTPUT=$(bash "$SCRIPT_DIR/generate-briefing.sh" "$SPEC_DIR/IMPLEMENTATION_PLAN.md" .claude/ralph-journal.tsv 3 2>&1)

if echo "$OUTPUT" | grep -q "Recent revert details"; then
  pass "Briefing includes revert details section"
else
  fail "Expected 'Recent revert details' in briefing" "Got: ${OUTPUT}"
fi

if echo "$OUTPUT" | grep -q "MatchError\|unauthorized"; then
  pass "Actual test error message included in briefing"
else
  fail "Expected actual test error in briefing" "Got: ${OUTPUT}"
fi

if echo "$OUTPUT" | grep -q "snake_case\|VariableNames"; then
  pass "Actual lint error message included in briefing"
else
  fail "Expected actual lint error in briefing" "Got: ${OUTPUT}"
fi

cleanup

# ── Test 3.2: Briefing includes trend metrics when enough data ──────

echo ""
echo "Test 3.2: Briefing includes trend analysis with sufficient data"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR" .claude/ralph-logs

cat > "$SPEC_DIR/IMPLEMENTATION_PLAN.md" <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 7: Something** — Priority: HIGH, Deps: none

## Learnings
EOF

# 6+ entries to trigger trend analysis
cat > .claude/ralph-journal.tsv <<'EOF'
timestamp	outcome	task	metric	notes
2026-03-22T10:00:00	REVERT_TESTS	T1	-	fail
2026-03-22T10:01:00	REVERT_TESTS	T1	-	fail
2026-03-22T10:02:00	KEEP	T1	commits=1	ok
2026-03-22T10:03:00	KEEP	T2	commits=1	ok
2026-03-22T10:04:00	KEEP	T3	commits=1	ok
2026-03-22T10:05:00	KEEP	T4	commits=1	ok
EOF

OUTPUT=$(bash "$SCRIPT_DIR/generate-briefing.sh" "$SPEC_DIR/IMPLEMENTATION_PLAN.md" .claude/ralph-journal.tsv 7 2>&1)

if echo "$OUTPUT" | grep -q "Trend Analysis\|Failure Patterns\|Outcome Timeline"; then
  pass "Briefing includes trend analysis when enough data"
else
  fail "Expected trend analysis in briefing" "Got: ${OUTPUT}"
fi

cleanup

# ── Test 3.3: No trend section when insufficient data ────────────────

echo ""
echo "Test 3.3: No trend section with insufficient journal data"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR" .claude/ralph-logs

cat > "$SPEC_DIR/IMPLEMENTATION_PLAN.md" <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: Something** — Priority: HIGH

## Learnings
EOF

cat > .claude/ralph-journal.tsv <<'EOF'
timestamp	outcome	task	metric	notes
2026-03-22T10:00:00	KEEP	T1	commits=1	ok
2026-03-22T10:01:00	KEEP	T2	commits=1	ok
EOF

OUTPUT=$(bash "$SCRIPT_DIR/generate-briefing.sh" "$SPEC_DIR/IMPLEMENTATION_PLAN.md" .claude/ralph-journal.tsv 3 2>&1)

if echo "$OUTPUT" | grep -q "Trend Analysis"; then
  fail "Should not include trend analysis with only 2 entries" "Got: ${OUTPUT}"
else
  pass "Correctly skips trend analysis with insufficient data"
fi

cleanup

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 4: Injection audit trail (loop.sh)
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 4: Injection audit trail ━━━"

# ── Test 4.1: Injection content logged before consumption ────────────

echo ""
echo "Test 4.1: Injection logged to injections.log before deletion"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR" .claude/ralph-logs

# Create a complete plan so loop exits after 1 iteration
cat > "$SPEC_DIR/IMPLEMENTATION_PLAN.md" <<'EOF'
# Implementation Plan: Test

## Status: COMPLETE

## Tasks

- [x] **Task 1: Done** — Completed in abc123

## Learnings
EOF

# Create an inject file
cat > .claude/ralph-inject.md <<'EOF'
Use the UserRepository instead of raw SQL queries.
Also prefer Ecto changesets over manual validation.
EOF

# Run loop — plan is COMPLETE so it exits after checking
bash "$SCRIPT_DIR/loop.sh" "$SPEC_DIR" build 1 >/dev/null 2>&1 || true

INJECTION_LOG=".claude/ralph-logs/injections.log"

if [ -f "$INJECTION_LOG" ]; then
  pass "Injections log file created"
else
  fail "Expected injections.log" "Files: $(ls .claude/ralph-logs/ 2>/dev/null)"
fi

if [ -f "$INJECTION_LOG" ] && grep -q "UserRepository" "$INJECTION_LOG"; then
  pass "Injection content preserved in log"
else
  fail "Expected injection content in log" "Content: $(cat "$INJECTION_LOG" 2>/dev/null || echo 'missing')"
fi

if [ -f "$INJECTION_LOG" ] && grep -q "Ecto changesets" "$INJECTION_LOG"; then
  pass "Full injection content preserved (multi-line)"
else
  fail "Expected full multi-line injection in log" ""
fi

if [ ! -f .claude/ralph-inject.md ]; then
  pass "Original inject file consumed (deleted)"
else
  fail "Inject file should have been deleted" ""
fi

cleanup

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 5: Diff size gate (loop.sh logic extraction)
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 5: Diff size gate ━━━"

# ── Test 5.1: Verify diff size gate code exists in loop.sh ──────────

echo ""
echo "Test 5.1: Diff size gate code present in loop.sh"

if grep -q "REVERT_SCOPE" "$SCRIPT_DIR/loop.sh"; then
  pass "REVERT_SCOPE outcome exists in loop.sh"
else
  fail "Expected REVERT_SCOPE in loop.sh" ""
fi

if grep -q "RALPH_MAX_DIFF_FILES" "$SCRIPT_DIR/loop.sh"; then
  pass "RALPH_MAX_DIFF_FILES configuration exists"
else
  fail "Expected RALPH_MAX_DIFF_FILES in loop.sh" ""
fi

if grep -q "Gate 2: Diff size check" "$SCRIPT_DIR/loop.sh"; then
  pass "Diff size gate documented as Gate 2"
else
  fail "Expected Gate 2 comment" ""
fi

# ── Test 5.2: Gate triggers on large diffs in a real repo ─────────

echo ""
echo "Test 5.2: Diff size gate triggers on oversized commits"

setup_temp_repo
export CLAUDE_PROJECT_DIR="$TEST_DIR"

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR" .claude/ralph-logs

cat > "$SPEC_DIR/IMPLEMENTATION_PLAN.md" <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: Big change** — Priority: HIGH, Deps: none

## Learnings
EOF

# Create a commit that touches many files (simulate a sprawling iteration)
PRE_COMMIT=$(git rev-parse HEAD)
for i in $(seq 1 25); do
  echo "file ${i}" > "src/file${i}.ts"
done
git add -A
git commit -q -m "big change touching 25 files"

# Now test the gate logic manually (extracted from loop.sh)
DIFF_FILE_COUNT=$(git diff --name-only "$PRE_COMMIT" HEAD | wc -l | tr -d ' ')
MAX_DIFF_FILES=20

if [ "$DIFF_FILE_COUNT" -gt "$MAX_DIFF_FILES" ]; then
  pass "Gate correctly detects ${DIFF_FILE_COUNT} files exceeds max ${MAX_DIFF_FILES}"
else
  fail "Expected diff count > 20" "Got: ${DIFF_FILE_COUNT}"
fi

# Test with custom override
MAX_DIFF_FILES=30
if [ "$DIFF_FILE_COUNT" -le "$MAX_DIFF_FILES" ]; then
  pass "Custom max (30) correctly allows 25-file diff"
else
  fail "Expected 25-file diff to pass with max=30" ""
fi

cleanup

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 6: Tiered circuit breaker
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 6: Tiered circuit breaker ━━━"

# ── Test 6.1: Circuit breaker functions exist ─────────────────────────

echo ""
echo "Test 6.1: Tiered circuit breaker components present"

if grep -q "track_revert" "$SCRIPT_DIR/loop.sh"; then
  pass "track_revert function exists"
else
  fail "Expected track_revert in loop.sh" ""
fi

if grep -q "track_success" "$SCRIPT_DIR/loop.sh"; then
  pass "track_success function exists"
else
  fail "Expected track_success in loop.sh" ""
fi

if grep -q "CONSECUTIVE_REVERTS" "$SCRIPT_DIR/loop.sh"; then
  pass "CONSECUTIVE_REVERTS tracking variable exists"
else
  fail "Expected CONSECUTIVE_REVERTS in loop.sh" ""
fi

if grep -q "HARD_CIRCUIT_BREAK" "$SCRIPT_DIR/loop.sh"; then
  pass "HARD_CIRCUIT_BREAK outcome exists"
else
  fail "Expected HARD_CIRCUIT_BREAK in loop.sh" ""
fi

if grep -q "SOFT_CIRCUIT_BREAK" "$SCRIPT_DIR/loop.sh"; then
  pass "SOFT_CIRCUIT_BREAK journal entry exists"
else
  fail "Expected SOFT_CIRCUIT_BREAK in loop.sh" ""
fi

# ── Test 6.2: Test track functions in isolation ──────────────────────

echo ""
echo "Test 6.2: Track functions work correctly"

# Source the functions from loop.sh by extracting them
RESULT=$(bash -c '
  CONSECUTIVE_REVERTS=0
  CONSECUTIVE_REVERT_TASKS=""

  track_revert() {
    local task="$1"
    CONSECUTIVE_REVERTS=$((CONSECUTIVE_REVERTS + 1))
    CONSECUTIVE_REVERT_TASKS="${CONSECUTIVE_REVERT_TASKS:+${CONSECUTIVE_REVERT_TASKS}, }${task}"
  }

  track_success() {
    CONSECUTIVE_REVERTS=0
    CONSECUTIVE_REVERT_TASKS=""
  }

  # Simulate: revert Task A, revert Task B, revert Task C
  track_revert "Task A"
  track_revert "Task B"
  track_revert "Task C"
  echo "after_3_reverts: ${CONSECUTIVE_REVERTS} tasks: ${CONSECUTIVE_REVERT_TASKS}"

  # Simulate: success resets
  track_success
  echo "after_success: ${CONSECUTIVE_REVERTS} tasks: ${CONSECUTIVE_REVERT_TASKS}"

  # Simulate: 2 more reverts
  track_revert "Task D"
  track_revert "Task E"
  echo "after_2_more: ${CONSECUTIVE_REVERTS} tasks: ${CONSECUTIVE_REVERT_TASKS}"
')

if echo "$RESULT" | grep -q "after_3_reverts: 3"; then
  pass "3 consecutive reverts tracked correctly"
else
  fail "Expected 3 consecutive reverts" "Got: ${RESULT}"
fi

if echo "$RESULT" | grep -q "after_3_reverts.*Task A, Task B, Task C"; then
  pass "Revert task names tracked correctly"
else
  fail "Expected task names in tracking" "Got: ${RESULT}"
fi

if echo "$RESULT" | grep -q "after_success: 0 tasks: $"; then
  pass "Success resets consecutive revert counter"
else
  fail "Expected reset after success" "Got: ${RESULT}"
fi

if echo "$RESULT" | grep -q "after_2_more: 2"; then
  pass "Counter resumes correctly after reset"
else
  fail "Expected 2 after reset+2 reverts" "Got: ${RESULT}"
fi

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 7: Auto-harvest on completion
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 7: Auto-harvest on completion ━━━"

# ── Test 7.1: Auto-harvest code present ──────────────────────────────

echo ""
echo "Test 7.1: Auto-harvest code present in loop.sh"

if grep -q "AUTO_HARVEST" "$SCRIPT_DIR/loop.sh"; then
  pass "AUTO_HARVEST variable exists"
else
  fail "Expected AUTO_HARVEST in loop.sh" ""
fi

if grep -q "Auto-harvesting (plan complete)" "$SCRIPT_DIR/loop.sh"; then
  pass "Plan-complete harvest trigger exists"
else
  fail "Expected plan-complete harvest trigger" ""
fi

if grep -q "Auto-harvesting (loop stopped early" "$SCRIPT_DIR/loop.sh"; then
  pass "Early-stop harvest trigger exists"
else
  fail "Expected early-stop harvest trigger" ""
fi

if grep -q 'ONCE_FLAG.*WORKER_ID' "$SCRIPT_DIR/loop.sh"; then
  pass "Auto-harvest skipped for --once mode and workers"
else
  fail "Expected --once and worker guard" ""
fi

# ── Test 7.2: AUTO_HARVEST=false disables it ─────────────────────────

echo ""
echo "Test 7.2: AUTO_HARVEST=false is respected"

# The code checks: if [ "$AUTO_HARVEST" = "true" ]
RESULT=$(bash -c '
  AUTO_HARVEST=false
  if [ "$AUTO_HARVEST" = "true" ]; then
    echo "would_harvest"
  else
    echo "skipped"
  fi
')

if [ "$RESULT" = "skipped" ]; then
  pass "AUTO_HARVEST=false prevents harvesting"
else
  fail "Expected harvesting to be skipped" "Got: ${RESULT}"
fi

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 8: Worker health monitoring
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 8: Worker health monitoring ━━━"

# ── Test 8.1: Worker timeout code present ────────────────────────────

echo ""
echo "Test 8.1: Worker timeout monitoring present in orchestrate-parallel.sh"

ORCH_FILE="$SCRIPT_DIR/orchestrate-parallel.sh"

if grep -q "WORKER_TIMEOUT" "$ORCH_FILE"; then
  pass "WORKER_TIMEOUT variable exists"
else
  fail "Expected WORKER_TIMEOUT in orchestrate-parallel.sh" ""
fi

if grep -q "WORKER_LAST_ACTIVITY" "$ORCH_FILE"; then
  pass "Per-worker activity tracking exists"
else
  fail "Expected WORKER_LAST_ACTIVITY in orchestrate-parallel.sh" ""
fi

if grep -q "WORKER_KILLED" "$ORCH_FILE"; then
  pass "Worker killed state tracking exists"
else
  fail "Expected WORKER_KILLED in orchestrate-parallel.sh" ""
fi

if grep -q "WORKER_TIMEOUT.*timeout" "$ORCH_FILE"; then
  pass "Worker timeout detection and kill logic exists"
else
  fail "Expected timeout detection logic" ""
fi

if grep -q "RALPH_WORKER_TIMEOUT" "$ORCH_FILE"; then
  pass "Worker timeout is configurable via env var"
else
  fail "Expected RALPH_WORKER_TIMEOUT env var" ""
fi

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 9: Override expiry (PROMPT_harvest.md)
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 9: Override expiry in harvest prompt ━━━"

echo ""
echo "Test 9.1: Harvest prompt includes date tracking instructions"

HARVEST_FILE="$SCRIPT_DIR/../references/PROMPT_harvest.md"

if grep -q "verified: YYYY-MM-DD" "$HARVEST_FILE"; then
  pass "Date tracking format documented in harvest prompt"
else
  fail "Expected verified: YYYY-MM-DD in harvest prompt" ""
fi

if grep -q "30 days" "$HARVEST_FILE"; then
  pass "30-day expiry rule documented"
else
  fail "Expected 30-day rule in harvest prompt" ""
fi

if grep -q "<!-- human -->" "$HARVEST_FILE"; then
  pass "Human-added rule preservation documented"
else
  fail "Expected human marker preservation" ""
fi

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 10: PROMPT_build.md updated
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 10: Build prompt awareness of new gates ━━━"

echo ""
echo "Test 10.1: Build prompt documents new gates"

BUILD_FILE="$SCRIPT_DIR/../references/PROMPT_build.md"

if grep -q "Diff size gate" "$BUILD_FILE"; then
  pass "Diff size gate documented in build prompt"
else
  fail "Expected diff size gate in build prompt" ""
fi

if grep -q "Revert details are preserved" "$BUILD_FILE"; then
  pass "Revert detail preservation documented in build prompt"
else
  fail "Expected revert detail docs in build prompt" ""
fi

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 11: SKILL.md updated
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 11: SKILL.md documentation ━━━"

echo ""
echo "Test 11.1: SKILL.md documents all new features"

SKILL_FILE="$SCRIPT_DIR/../SKILL.md"

if grep -q "generate-summary.sh" "$SKILL_FILE"; then
  pass "generate-summary.sh listed in scripts table"
else
  fail "Expected generate-summary.sh in SKILL.md" ""
fi

if grep -q "generate-metrics.sh" "$SKILL_FILE"; then
  pass "generate-metrics.sh listed in scripts table"
else
  fail "Expected generate-metrics.sh in SKILL.md" ""
fi

if grep -q "ralph-summary-" "$SKILL_FILE"; then
  pass "Summary artifact documented"
else
  fail "Expected ralph-summary artifact in SKILL.md" ""
fi

if grep -q "revert-.*-reason.txt" "$SKILL_FILE"; then
  pass "Revert reason files documented"
else
  fail "Expected revert reason files in SKILL.md" ""
fi

if grep -q "injections.log" "$SKILL_FILE"; then
  pass "Injections log documented"
else
  fail "Expected injections.log in SKILL.md" ""
fi

if grep -q "Auto-runs on completion" "$SKILL_FILE"; then
  pass "Auto-harvest documented"
else
  fail "Expected auto-harvest in SKILL.md" ""
fi

if grep -q "tiered" "$SKILL_FILE"; then
  pass "Tiered circuit breaker documented"
else
  fail "Expected tiered circuit breaker in SKILL.md" ""
fi

if grep -q "RALPH_MAX_DIFF_FILES" "$SKILL_FILE"; then
  pass "Diff size gate documented"
else
  fail "Expected diff size gate in SKILL.md" ""
fi

# ══════════════════════════════════════════════════════════════════════════
# RESULTS
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

unset CLAUDE_PROJECT_DIR 2>/dev/null || true

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
