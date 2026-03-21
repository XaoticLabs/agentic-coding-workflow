#!/usr/bin/env bash
# Test suite for Ralph parallel mode components
# Runs in a temporary git repo to avoid polluting the real one
#
# Usage: bash test-parallel.sh
#
# Tests:
#   1. partition-tasks.sh — file affinity, load balancing, no-files fallback
#   2. merge-workers.sh — clean merge, conflict detection
#   3. loop.sh — completion marker writing

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
# TEST GROUP 1: partition-tasks.sh
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 1: partition-tasks.sh ━━━"

# ── Test 1.1: File affinity groups tasks by shared files ────────────────

echo ""
echo "Test 1.1: File affinity groups tasks sharing files onto the same worker"

setup_temp_repo

mkdir -p .claude/specs/test
cat > .claude/specs/test/IMPLEMENTATION_PLAN.md <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: Auth login** — Priority: HIGH, Deps: none, Spec: 01-auth.md, Files: src/auth/login.ts src/auth/types.ts
- [ ] **Task 2: Auth session** — Priority: HIGH, Deps: none, Spec: 02-auth.md, Files: src/auth/session.ts src/auth/types.ts
- [ ] **Task 3: API routes** — Priority: MEDIUM, Deps: none, Spec: 03-api.md, Files: src/api/routes.ts src/api/handlers.ts
- [ ] **Task 4: API middleware** — Priority: MEDIUM, Deps: none, Spec: 04-api.md, Files: src/api/middleware.ts src/api/routes.ts

## Learnings
EOF

OUTPUT=$(bash "$SCRIPT_DIR/partition-tasks.sh" .claude/specs/test/IMPLEMENTATION_PLAN.md 2)

# Tasks 1 and 2 share src/auth/types.ts — should be on the same worker
WORKER_0_TASKS=$(echo "$OUTPUT" | grep '"worker-0"' | head -1)
WORKER_1_TASKS=$(echo "$OUTPUT" | grep '"worker-1"' | head -1)

# Check that tasks 1 and 2 are together (both auth, share types.ts)
if echo "$WORKER_0_TASKS" | grep -q "1" && echo "$WORKER_0_TASKS" | grep -q "2"; then
  pass "Tasks 1 & 2 (sharing auth/types.ts) assigned to same worker (worker-0)"
elif echo "$WORKER_1_TASKS" | grep -q "1" && echo "$WORKER_1_TASKS" | grep -q "2"; then
  pass "Tasks 1 & 2 (sharing auth/types.ts) assigned to same worker (worker-1)"
else
  fail "Tasks 1 & 2 should be on the same worker (share auth/types.ts)" \
    "Got: worker-0=${WORKER_0_TASKS}, worker-1=${WORKER_1_TASKS}"
fi

# Check that tasks 3 and 4 are together (both api, share routes.ts)
if echo "$WORKER_0_TASKS" | grep -q "3" && echo "$WORKER_0_TASKS" | grep -q "4"; then
  pass "Tasks 3 & 4 (sharing api/routes.ts) assigned to same worker (worker-0)"
elif echo "$WORKER_1_TASKS" | grep -q "3" && echo "$WORKER_1_TASKS" | grep -q "4"; then
  pass "Tasks 3 & 4 (sharing api/routes.ts) assigned to same worker (worker-1)"
else
  fail "Tasks 3 & 4 should be on the same worker (share api/routes.ts)" \
    "Got: worker-0=${WORKER_0_TASKS}, worker-1=${WORKER_1_TASKS}"
fi

# Check auth tasks and api tasks are on DIFFERENT workers
AUTH_WORKER=""
API_WORKER=""
if echo "$WORKER_0_TASKS" | grep -q "1"; then AUTH_WORKER="0"; else AUTH_WORKER="1"; fi
if echo "$WORKER_0_TASKS" | grep -q "3"; then API_WORKER="0"; else API_WORKER="1"; fi

if [ "$AUTH_WORKER" != "$API_WORKER" ]; then
  pass "Auth tasks and API tasks assigned to different workers"
else
  fail "Auth tasks and API tasks should be on different workers" \
    "Both on worker-${AUTH_WORKER}"
fi

cleanup

# ── Test 1.2: No file overlap — falls back to load balancing ───────────

echo ""
echo "Test 1.2: Tasks without file overlap are load-balanced"

setup_temp_repo

mkdir -p .claude/specs/test
cat > .claude/specs/test/IMPLEMENTATION_PLAN.md <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: Feature A** — Priority: HIGH, Deps: none, Spec: 01.md, Files: src/a.ts
- [ ] **Task 2: Feature B** — Priority: HIGH, Deps: none, Spec: 02.md, Files: src/b.ts
- [ ] **Task 3: Feature C** — Priority: MEDIUM, Deps: none, Spec: 03.md, Files: src/c.ts
- [ ] **Task 4: Feature D** — Priority: MEDIUM, Deps: none, Spec: 04.md, Files: src/d.ts

## Learnings
EOF

OUTPUT=$(bash "$SCRIPT_DIR/partition-tasks.sh" .claude/specs/test/IMPLEMENTATION_PLAN.md 2)

# With no overlap and 4 tasks / 2 workers, each worker should get 2 tasks
# Extract the array content between brackets and count comma-separated items
W0_LINE=$(echo "$OUTPUT" | grep '"worker-0"' | head -1)
W0_ARRAY=$(echo "$W0_LINE" | sed 's/.*\[\(.*\)\].*/\1/' | tr -d ' ')
W0_COUNT=$(echo "$W0_ARRAY" | tr ',' '\n' | grep -c '[0-9]' || echo 0)

W1_LINE=$(echo "$OUTPUT" | grep '"worker-1"' | head -1)
W1_ARRAY=$(echo "$W1_LINE" | sed 's/.*\[\(.*\)\].*/\1/' | tr -d ' ')
W1_COUNT=$(echo "$W1_ARRAY" | tr ',' '\n' | grep -c '[0-9]' || echo 0)

if [ "$W0_COUNT" -eq 2 ] && [ "$W1_COUNT" -eq 2 ]; then
  pass "Load balanced: 2 tasks per worker"
else
  fail "Expected 2 tasks per worker" "Got: worker-0=${W0_COUNT}, worker-1=${W1_COUNT}"
fi

cleanup

# ── Test 1.3: Tasks without Files: field ────────────────────────────────

echo ""
echo "Test 1.3: Tasks missing Files: field still get assigned"

setup_temp_repo

mkdir -p .claude/specs/test
cat > .claude/specs/test/IMPLEMENTATION_PLAN.md <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: Feature A** — Priority: HIGH, Deps: none, Spec: 01.md
- [ ] **Task 2: Feature B** — Priority: HIGH, Deps: none, Spec: 02.md
- [ ] **Task 3: Feature C** — Priority: MEDIUM, Deps: none, Spec: 03.md

## Learnings
EOF

OUTPUT=$(bash "$SCRIPT_DIR/partition-tasks.sh" .claude/specs/test/IMPLEMENTATION_PLAN.md 2)

# All 3 tasks should appear in worker assignments
TOTAL=$(echo "$OUTPUT" | grep '"total_incomplete"' | grep -o '[0-9]*')

if [ "$TOTAL" -eq 3 ]; then
  pass "All 3 tasks assigned despite missing Files: field"
else
  fail "Expected 3 tasks total" "Got: ${TOTAL}"
fi

cleanup

# ── Test 1.4: Completed tasks are skipped ───────────────────────────────

echo ""
echo "Test 1.4: Completed tasks are excluded"

setup_temp_repo

mkdir -p .claude/specs/test
cat > .claude/specs/test/IMPLEMENTATION_PLAN.md <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [x] **Task 1: Done** — Priority: HIGH, Deps: none, Spec: 01.md, Files: src/a.ts
- [ ] **Task 2: Todo** — Priority: HIGH, Deps: none, Spec: 02.md, Files: src/b.ts
- [x] **Task 3: Also done** — Priority: MEDIUM, Deps: none, Spec: 03.md, Files: src/c.ts

## Learnings
EOF

OUTPUT=$(bash "$SCRIPT_DIR/partition-tasks.sh" .claude/specs/test/IMPLEMENTATION_PLAN.md 2)

TOTAL=$(echo "$OUTPUT" | grep '"total_incomplete"' | grep -o '[0-9]*')

if [ "$TOTAL" -eq 1 ]; then
  pass "Only 1 incomplete task found (2 completed skipped)"
else
  fail "Expected 1 incomplete task" "Got: ${TOTAL}"
fi

cleanup

# ── Test 1.5: All complete returns empty ────────────────────────────────

echo ""
echo "Test 1.5: All tasks complete returns empty result"

setup_temp_repo

mkdir -p .claude/specs/test
cat > .claude/specs/test/IMPLEMENTATION_PLAN.md <<'EOF'
# Implementation Plan: Test

## Status: COMPLETE

## Tasks

- [x] **Task 1: Done** — Priority: HIGH, Deps: none, Spec: 01.md, Files: src/a.ts

## Learnings
EOF

OUTPUT=$(bash "$SCRIPT_DIR/partition-tasks.sh" .claude/specs/test/IMPLEMENTATION_PLAN.md 2)

if echo "$OUTPUT" | grep -q '"All tasks complete"'; then
  pass "All-complete plan returns note"
else
  fail "Expected 'All tasks complete' note" "Got: ${OUTPUT}"
fi

cleanup

# ── Test 1.6: file_owners in output ─────────────────────────────────────

echo ""
echo "Test 1.6: Output includes file_owners map"

setup_temp_repo

mkdir -p .claude/specs/test
cat > .claude/specs/test/IMPLEMENTATION_PLAN.md <<'EOF'
# Implementation Plan: Test

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: Auth** — Priority: HIGH, Deps: none, Spec: 01.md, Files: src/auth.ts src/types.ts

## Learnings
EOF

OUTPUT=$(bash "$SCRIPT_DIR/partition-tasks.sh" .claude/specs/test/IMPLEMENTATION_PLAN.md 2)

if echo "$OUTPUT" | grep -q '"file_owners"'; then
  pass "Output contains file_owners section"
else
  fail "Expected file_owners in output" "Got: ${OUTPUT}"
fi

if echo "$OUTPUT" | grep -q 'src/auth.ts'; then
  pass "file_owners includes src/auth.ts"
else
  fail "Expected src/auth.ts in file_owners" "Got: ${OUTPUT}"
fi

cleanup

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 2: merge-workers.sh
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 2: merge-workers.sh ━━━"

# ── Test 2.1: Clean merge of non-conflicting branches ──────────────────

echo ""
echo "Test 2.1: Clean merge of non-conflicting worker branches"

setup_temp_repo

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR"
echo "# plan" > "$SPEC_DIR/IMPLEMENTATION_PLAN.md"

# Create worker-0 branch: adds file A
git checkout -q -b ralph/test/worker-0
echo "module A" > src/moduleA.ts
git add src/moduleA.ts
git commit -q -m "worker-0: add module A"

# Create worker-1 branch: adds file B
git checkout -q main
git checkout -q -b ralph/test/worker-1
echo "module B" > src/moduleB.ts
git add src/moduleB.ts
git commit -q -m "worker-1: add module B"

# Go back to main for merge
git checkout -q main

# Run merge (without Claude — conflicts would fail, but we expect clean merge)
MERGE_OUTPUT=$(bash "$SCRIPT_DIR/merge-workers.sh" test 2 main "$SPEC_DIR" 2>&1 || true)
if echo "$MERGE_OUTPUT" | grep -q "Merge complete"; then
  pass "Clean merge completed successfully"
else
  fail "Clean merge should succeed" "Output: ${MERGE_OUTPUT}"
fi

# Verify both files exist on main
if [ -f src/moduleA.ts ] && [ -f src/moduleB.ts ]; then
  pass "Both worker files present after merge"
else
  fail "Expected both moduleA.ts and moduleB.ts on main" \
    "A exists: $([ -f src/moduleA.ts ] && echo yes || echo no), B exists: $([ -f src/moduleB.ts ] && echo yes || echo no)"
fi

cleanup

# ── Test 2.2: Skips branches with no new commits ───────────────────────

echo ""
echo "Test 2.2: Skips worker branches with no new commits"

setup_temp_repo

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR"
echo "# plan" > "$SPEC_DIR/IMPLEMENTATION_PLAN.md"

# Create worker-0 with a commit
git checkout -q -b ralph/test/worker-0
echo "work" > src/work.ts
git add src/work.ts
git commit -q -m "worker-0: real work"

# Create worker-1 with NO new commits (same as main)
git checkout -q main
git checkout -q -b ralph/test/worker-1

git checkout -q main

OUTPUT=$(bash "$SCRIPT_DIR/merge-workers.sh" test 2 main "$SPEC_DIR" 2>&1)

if echo "$OUTPUT" | grep -q "worker-1.*no new commits"; then
  pass "Worker-1 (no commits) correctly skipped"
else
  fail "Expected worker-1 to be skipped" "Got: ${OUTPUT}"
fi

if [ -f src/work.ts ]; then
  pass "Worker-0 changes still merged"
else
  fail "Expected worker-0 changes on main" ""
fi

cleanup

# ── Test 2.3: Detects missing branches ──────────────────────────────────

echo ""
echo "Test 2.3: Handles missing worker branches gracefully"

setup_temp_repo

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR"
echo "# plan" > "$SPEC_DIR/IMPLEMENTATION_PLAN.md"

# Only create worker-0, not worker-1
git checkout -q -b ralph/test/worker-0
echo "work" > src/work.ts
git add src/work.ts
git commit -q -m "worker-0: work"
git checkout -q main

OUTPUT=$(bash "$SCRIPT_DIR/merge-workers.sh" test 2 main "$SPEC_DIR" 2>&1)

if echo "$OUTPUT" | grep -q "worker-1.*SKIPPED.*not found"; then
  pass "Missing branch reported as skipped"
else
  fail "Expected missing branch warning" "Got: ${OUTPUT}"
fi

cleanup

# ── Test 2.4: Detects conflicts ─────────────────────────────────────────

echo ""
echo "Test 2.4: Detects merge conflicts (without Claude, merge fails)"

setup_temp_repo

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR"
echo "# plan" > "$SPEC_DIR/IMPLEMENTATION_PLAN.md"

# Both workers modify the same file differently
git checkout -q -b ralph/test/worker-0
echo "version A" > src/index.ts
git add src/index.ts
git commit -q -m "worker-0: modify index"

git checkout -q main
git checkout -q -b ralph/test/worker-1
echo "version B" > src/index.ts
git add src/index.ts
git commit -q -m "worker-1: modify index"

git checkout -q main

# This should fail because Claude isn't available to resolve
OUTPUT=$(bash "$SCRIPT_DIR/merge-workers.sh" test 2 main "$SPEC_DIR" 2>&1 || true)

if echo "$OUTPUT" | grep -q "CONFLICT\|conflict\|FAILED"; then
  pass "Conflict correctly detected"
else
  fail "Expected conflict detection" "Got: ${OUTPUT}"
fi

cleanup

# ══════════════════════════════════════════════════════════════════════════
# TEST GROUP 3: loop.sh completion marker
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━ Test Group 3: loop.sh completion marker ━━━"

# ── Test 3.1: Marker written when RALPH_WORKER_ID is set ───────────────

echo ""
echo "Test 3.1: Completion marker written when RALPH_WORKER_ID is set"

setup_temp_repo

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR" .claude/ralph-logs

# Create a plan that's already COMPLETE so loop exits immediately
cat > "$SPEC_DIR/IMPLEMENTATION_PLAN.md" <<'EOF'
# Implementation Plan: Test

## Status: COMPLETE

## Tasks

- [x] **Task 1: Done** — Priority: HIGH, Deps: none, Spec: 01.md, Files: src/a.ts

## Learnings
EOF

# Run loop.sh with RALPH_WORKER_ID set — it should exit immediately (plan complete)
export RALPH_WORKER_ID="worker-42"
export CLAUDE_PROJECT_DIR="$TEST_DIR"

# loop.sh build mode — should see "All tasks complete!" and exit
OUTPUT=$(bash "$SCRIPT_DIR/loop.sh" "$SPEC_DIR" build 1 2>&1 || true)

MARKER=".claude/ralph-worker-done-worker-42"

if [ -f "$MARKER" ]; then
  pass "Completion marker file created"
else
  fail "Expected marker at ${MARKER}" "Files in .claude/: $(ls .claude/ 2>/dev/null)"
fi

if [ -f "$MARKER" ] && grep -q '"worker": "worker-42"' "$MARKER"; then
  pass "Marker contains correct worker ID"
else
  fail "Expected worker ID in marker" "Content: $(cat "$MARKER" 2>/dev/null || echo 'file missing')"
fi

if [ -f "$MARKER" ] && grep -q '"status": "done"' "$MARKER"; then
  pass "Marker contains done status"
else
  fail "Expected done status in marker" "Content: $(cat "$MARKER" 2>/dev/null || echo 'file missing')"
fi

unset RALPH_WORKER_ID
unset CLAUDE_PROJECT_DIR

cleanup

# ── Test 3.2: No marker when RALPH_WORKER_ID is NOT set ────────────────

echo ""
echo "Test 3.2: No completion marker when RALPH_WORKER_ID is not set"

setup_temp_repo

SPEC_DIR=".claude/specs/test"
mkdir -p "$SPEC_DIR" .claude/ralph-logs

cat > "$SPEC_DIR/IMPLEMENTATION_PLAN.md" <<'EOF'
# Implementation Plan: Test

## Status: COMPLETE

## Tasks

- [x] **Task 1: Done** — Priority: HIGH, Deps: none, Spec: 01.md

## Learnings
EOF

export CLAUDE_PROJECT_DIR="$TEST_DIR"
unset RALPH_WORKER_ID 2>/dev/null || true

# Use timeout to prevent hanging (plan is COMPLETE so should exit in <5s)
if command -v timeout >/dev/null 2>&1; then
  timeout 10 bash "$SCRIPT_DIR/loop.sh" "$SPEC_DIR" build 1 >/dev/null 2>&1 || true
elif command -v gtimeout >/dev/null 2>&1; then
  gtimeout 10 bash "$SCRIPT_DIR/loop.sh" "$SPEC_DIR" build 1 >/dev/null 2>&1 || true
else
  bash "$SCRIPT_DIR/loop.sh" "$SPEC_DIR" build 1 >/dev/null 2>&1 || true
fi

MARKER_FILES=$(find .claude -name 'ralph-worker-done-*' 2>/dev/null || true)
MARKER_COUNT=0
if [ -n "$MARKER_FILES" ]; then
  MARKER_COUNT=$(echo "$MARKER_FILES" | wc -l | tr -d ' ')
fi

if [ "$MARKER_COUNT" -eq 0 ]; then
  pass "No marker created when RALPH_WORKER_ID not set"
else
  fail "Expected no marker files" "Found: ${MARKER_FILES}"
fi

unset CLAUDE_PROJECT_DIR

cleanup

# ══════════════════════════════════════════════════════════════════════════
# RESULTS
# ══════════════════════════════════════════════════════════════════════════

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
