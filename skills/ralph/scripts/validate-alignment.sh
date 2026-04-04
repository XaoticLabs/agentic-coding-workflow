#!/usr/bin/env bash
# Validate alignment between IMPLEMENTATION_PLAN.md acceptance criteria and spec files.
# Checks that each task's plan-level criteria have corresponding coverage in spec files.
#
# Usage: validate-alignment.sh <spec-dir>
# Output: warnings on stdout, exits 0 always (advisory, never blocks)

set -euo pipefail

SPEC_DIR="${1:?Usage: validate-alignment.sh <spec-dir>}"
PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"

if [ ! -f "$PLAN_FILE" ]; then
  echo "No IMPLEMENTATION_PLAN.md found — skipping alignment check."
  exit 0
fi

MISALIGNED=0
MISSING_SPECS=0

# Extract task entries and their spec file references
while IFS= read -r task_line; do
  # Parse task number and spec file
  TASK_NUM=$(echo "$task_line" | grep -oE 'Task [0-9]+' | head -1 | awk '{print $2}')
  SPEC_FILE=$(echo "$task_line" | grep -oE 'Spec: [^ ,]+' | sed 's/Spec: //' || true)

  [ -z "$TASK_NUM" ] && continue

  # Check spec file exists
  if [ -n "$SPEC_FILE" ]; then
    FULL_SPEC_PATH="${SPEC_DIR}/${SPEC_FILE}"
    if [ ! -f "$FULL_SPEC_PATH" ]; then
      echo "⚠ Task ${TASK_NUM}: references spec '${SPEC_FILE}' but file does not exist"
      MISSING_SPECS=$((MISSING_SPECS + 1))
      continue
    fi

    # Extract acceptance criteria from plan (between this task's section and the next)
    # Look for criteria in the ## Tasks detail section
    PLAN_CRITERIA=$(sed -n "/### Task ${TASK_NUM}:/,/### Task [0-9]/p" "$PLAN_FILE" 2>/dev/null \
      | grep -iE '(acceptance|criteria|must|should|verify)' \
      | head -10 || true)

    # Extract acceptance criteria from spec file
    SPEC_CRITERIA=$(grep -iE '(acceptance|criteria|must|should|verify)' "$FULL_SPEC_PATH" 2>/dev/null \
      | head -10 || true)

    # Simple divergence check: if plan has criteria but spec has none (or vice versa)
    PLAN_COUNT=$(echo "$PLAN_CRITERIA" | grep -c '[^ ]' 2>/dev/null || echo 0)
    SPEC_COUNT=$(echo "$SPEC_CRITERIA" | grep -c '[^ ]' 2>/dev/null || echo 0)

    if [ "$PLAN_COUNT" -gt 0 ] && [ "$SPEC_COUNT" -eq 0 ]; then
      echo "⚠ Task ${TASK_NUM}: plan has ${PLAN_COUNT} criteria lines but spec '${SPEC_FILE}' has none"
      MISALIGNED=$((MISALIGNED + 1))
    elif [ "$PLAN_COUNT" -eq 0 ] && [ "$SPEC_COUNT" -gt 0 ]; then
      echo "⚠ Task ${TASK_NUM}: spec '${SPEC_FILE}' has ${SPEC_COUNT} criteria lines but plan section has none"
      MISALIGNED=$((MISALIGNED + 1))
    fi

    # Check for significant count divergence (one has 3x more criteria than other)
    if [ "$PLAN_COUNT" -gt 0 ] && [ "$SPEC_COUNT" -gt 0 ]; then
      if [ "$PLAN_COUNT" -gt $((SPEC_COUNT * 3)) ] || [ "$SPEC_COUNT" -gt $((PLAN_COUNT * 3)) ]; then
        echo "⚠ Task ${TASK_NUM}: criteria count divergence — plan has ${PLAN_COUNT}, spec has ${SPEC_COUNT}"
        MISALIGNED=$((MISALIGNED + 1))
      fi
    fi
  fi
done < <(grep '^\- \[[ x]\] \*\*Task' "$PLAN_FILE" 2>/dev/null || true)

# Summary
if [ "$MISALIGNED" -gt 0 ] || [ "$MISSING_SPECS" -gt 0 ]; then
  echo ""
  echo "ALIGNMENT CHECK: ${MISALIGNED} misaligned task(s), ${MISSING_SPECS} missing spec file(s)."
  echo "The evaluator grades against plan criteria — if they drift from specs, evaluation may be unreliable."
  echo "Review and reconcile before running."
fi
