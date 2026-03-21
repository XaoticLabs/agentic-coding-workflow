#!/bin/bash
# Partition tasks from IMPLEMENTATION_PLAN.md into dependency waves for parallel execution
#
# Usage: partition-tasks.sh <plan-file> <num-workers>
# Output: JSON mapping worker IDs to task numbers
#
# Algorithm:
#   1. Parse all tasks and their dependencies
#   2. Group into waves (wave 0 = no deps, wave 1 = depends on wave 0, etc.)
#   3. Round-robin assign tasks within each wave to workers

set -euo pipefail

PLAN_FILE="${1:?Usage: partition-tasks.sh <plan-file> <num-workers>}"
NUM_WORKERS="${2:?Usage: partition-tasks.sh <plan-file> <num-workers>}"

if [ ! -f "$PLAN_FILE" ]; then
  echo "Error: Plan file not found: $PLAN_FILE" >&2
  exit 1
fi

# ── Parse tasks ─────────────────────────────────────────────────────────
# Expected format:
#   - [ ] **Task 1: Name** — Priority: HIGH, Deps: none, Spec: 01-topic.md
#   - [ ] **Task 2: Name** — Priority: HIGH, Deps: Task 1, Spec: 02-topic.md
#   - [x] **Task 3: Name** — (already done, skip)

declare -A task_deps
declare -A task_priority
declare -a incomplete_tasks

while IFS= read -r line; do
  # Skip completed tasks
  if echo "$line" | grep -q '^\- \[x\]'; then
    continue
  fi

  # Parse incomplete tasks
  if echo "$line" | grep -qP '^\- \[ \] \*\*Task (\d+)'; then
    task_num=$(echo "$line" | grep -oP 'Task \K\d+')
    deps=$(echo "$line" | grep -oP 'Deps: \K[^,]+(?=,)' || echo "none")
    priority=$(echo "$line" | grep -oP 'Priority: \K\w+' || echo "MEDIUM")

    incomplete_tasks+=("$task_num")
    task_priority[$task_num]="$priority"

    # Parse dependency list
    if [ "$deps" = "none" ] || [ "$deps" = "None" ] || [ -z "$deps" ]; then
      task_deps[$task_num]=""
    else
      # Extract task numbers from deps like "Task 1, Task 3"
      dep_nums=$(echo "$deps" | grep -oP '\d+' | tr '\n' ' ')
      task_deps[$task_num]="$dep_nums"
    fi
  fi
done < "$PLAN_FILE"

if [ ${#incomplete_tasks[@]} -eq 0 ]; then
  echo '{"workers": {}, "waves": [], "note": "All tasks complete"}'
  exit 0
fi

# ── Build dependency waves ──────────────────────────────────────────────

declare -A task_wave
declare -a waves
max_wave=0

# Assign waves: wave 0 = no deps, wave N = max(dep waves) + 1
assign_wave() {
  local task=$1

  # Already assigned
  if [ -n "${task_wave[$task]+x}" ]; then
    return
  fi

  local deps="${task_deps[$task]}"
  if [ -z "$deps" ]; then
    task_wave[$task]=0
    return
  fi

  local max_dep_wave=0
  for dep in $deps; do
    # If dependency is in incomplete list, recurse
    if [ -n "${task_deps[$dep]+x}" ]; then
      assign_wave "$dep"
      local dep_w=${task_wave[$dep]:-0}
      [ "$dep_w" -gt "$max_dep_wave" ] && max_dep_wave=$dep_w
    fi
    # If dependency is not in incomplete list, it's already done (wave -1 effectively)
  done

  task_wave[$task]=$((max_dep_wave + 1))
  [ "${task_wave[$task]}" -gt "$max_wave" ] && max_wave=${task_wave[$task]}
}

for task in "${incomplete_tasks[@]}"; do
  assign_wave "$task"
done

# ── Round-robin assign to workers ───────────────────────────────────────

# Build JSON output
echo "{"
echo "  \"workers\": {"

for ((w=0; w<NUM_WORKERS; w++)); do
  worker_tasks=""
  # Collect tasks assigned to this worker
  worker_idx=0
  for ((wave=0; wave<=max_wave; wave++)); do
    for task in "${incomplete_tasks[@]}"; do
      if [ "${task_wave[$task]}" -eq "$wave" ]; then
        if [ $((worker_idx % NUM_WORKERS)) -eq "$w" ]; then
          [ -n "$worker_tasks" ] && worker_tasks+=", "
          worker_tasks+="$task"
        fi
        worker_idx=$((worker_idx + 1))
      fi
    done
  done

  comma=""
  [ $((w + 1)) -lt "$NUM_WORKERS" ] && comma=","
  echo "    \"worker-${w}\": [${worker_tasks}]${comma}"
done

echo "  },"

# Output waves for reference
echo "  \"waves\": ["
for ((wave=0; wave<=max_wave; wave++)); do
  wave_tasks=""
  for task in "${incomplete_tasks[@]}"; do
    if [ "${task_wave[$task]}" -eq "$wave" ]; then
      [ -n "$wave_tasks" ] && wave_tasks+=", "
      wave_tasks+="$task"
    fi
  done
  comma=""
  [ $((wave + 1)) -le "$max_wave" ] && comma=","
  echo "    {\"wave\": ${wave}, \"tasks\": [${wave_tasks}]}${comma}"
done
echo "  ],"

echo "  \"total_incomplete\": ${#incomplete_tasks[@]},"
echo "  \"num_workers\": ${NUM_WORKERS}"
echo "}"
