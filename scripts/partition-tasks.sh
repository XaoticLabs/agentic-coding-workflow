#!/usr/bin/env bash
# Partition tasks from IMPLEMENTATION_PLAN.md into dependency waves for parallel execution
#
# Usage: partition-tasks.sh <plan-file> <num-workers>
# Output: JSON mapping worker IDs to task numbers
#
# Algorithm:
#   1. Parse all tasks, their dependencies, and file lists
#   2. Group into waves (wave 0 = no deps, wave 1 = depends on wave 0, etc.)
#   3. Assign tasks to workers using file-affinity: each file is owned by one worker,
#      tasks go to the worker that already owns the most of their files

set -euo pipefail

PLAN_FILE="${1:?Usage: partition-tasks.sh <plan-file> <num-workers>}"
NUM_WORKERS="${2:?Usage: partition-tasks.sh <plan-file> <num-workers>}"

if [ ! -f "$PLAN_FILE" ]; then
  echo "Error: Plan file not found: $PLAN_FILE" >&2
  exit 1
fi

# ── Parse tasks ─────────────────────────────────────────────────────────
# Expected format:
#   - [ ] **Task 1: Name** — Priority: HIGH, Deps: none, Spec: 01-topic.md, Files: src/a.ts src/b.ts
#   - [ ] **Task 2: Name** — Priority: HIGH, Deps: Task 1, Spec: 02-topic.md, Files: src/c.ts
#   - [x] **Task 3: Name** — (already done, skip)

declare -A task_deps
declare -A task_priority
declare -A task_files
declare -a incomplete_tasks=()

while IFS= read -r line; do
  # Skip completed tasks
  if echo "$line" | grep -q '^\- \[x\]'; then
    continue
  fi

  # Parse incomplete tasks
  if echo "$line" | grep -q '^\- \[ \] \*\*Task [0-9]'; then
    task_num=$(echo "$line" | sed -n 's/.*\*\*Task \([0-9]*\):.*/\1/p')
    deps=$(echo "$line" | sed -n 's/.*Deps: \([^,]*\),.*/\1/p')
    [ -z "$deps" ] && deps="none"
    priority=$(echo "$line" | sed -n 's/.*Priority: \([A-Z]*\).*/\1/p')
    [ -z "$priority" ] && priority="MEDIUM"
    files=$(echo "$line" | sed -n 's/.*Files: \(.*\)/\1/p')

    incomplete_tasks+=("$task_num")
    task_priority[$task_num]="$priority"
    task_files[$task_num]="$files"

    # Parse dependency list
    if [ "$deps" = "none" ] || [ "$deps" = "None" ] || [ -z "$deps" ]; then
      task_deps[$task_num]=""
    else
      # Extract task numbers from deps like "Task 1, Task 3"
      dep_nums=$(echo "$deps" | grep -o '[0-9]*' | tr '\n' ' ')
      task_deps[$task_num]="$dep_nums"
    fi
  fi
done < "$PLAN_FILE"

if [ ${#incomplete_tasks[@]} -eq 0 ]; then
  echo '{"workers": {}, "waves": [], "file_owners": {}, "note": "All tasks complete"}'
  exit 0
fi

# ── Build dependency waves ──────────────────────────────────────────────

declare -A task_wave
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
  if [ "${task_wave[$task]}" -gt "$max_wave" ]; then
    max_wave=${task_wave[$task]}
  fi
}

for task in "${incomplete_tasks[@]}"; do
  assign_wave "$task"
done

# ── Load conflict hotspots from parallel learnings ─────────────────────
# Hotspot files get pre-assigned to worker-0 so they're never split across workers.
declare -A hotspot_files=()
_PARTITION_SLUG=$(basename "$(dirname "$PLAN_FILE")")
LEARNINGS_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/ralph/${_PARTITION_SLUG}/learnings.json"
if [ -f "$LEARNINGS_FILE" ]; then
  while IFS= read -r hfile; do
    [ -n "$hfile" ] && hotspot_files["$hfile"]=1
  done < <(python3 -c "
import json, sys
try:
    data = json.load(open('${LEARNINGS_FILE}'))
    for f, info in data.get('conflict_hotspots', {}).items():
        if info.get('conflicts', 0) >= 2:
            print(f)
except: pass
" 2>/dev/null || true)
  if [ "${#hotspot_files[@]}" -gt 0 ]; then
    echo "Loaded ${#hotspot_files[@]} conflict hotspot(s) from parallel learnings" >&2
  fi
fi

# ── File-affinity assignment ────────────────────────────────────────────
# For each task (processed wave-by-wave):
#   - Count how many of the task's files are already owned by each worker
#   - Assign to worker with most overlap; ties broken by lowest task count
#   - If no overlap, assign to worker with fewest tasks (load balance)
#   - Register all task files under the assigned worker
#   - Conflict hotspot files get extra affinity weight (2x) to prevent splitting

declare -A file_owner=()     # file path -> worker index
file_owner_count=0           # track count separately to avoid bash unbound issues
declare -A worker_task_count # worker index -> number of tasks assigned
declare -A task_assignment   # task num -> worker index

# Initialize worker task counts
for ((w=0; w<NUM_WORKERS; w++)); do
  worker_task_count[$w]=0
done

# Process tasks wave by wave (respects dependencies)
for ((wave=0; wave<=max_wave; wave++)); do
  for task in "${incomplete_tasks[@]}"; do
    if [ "${task_wave[$task]}" -ne "$wave" ]; then
      continue
    fi

    files="${task_files[$task]}"

    # If no files listed, fall back to load-balanced assignment
    if [ -z "$files" ]; then
      # Assign to worker with fewest tasks
      min_count=999999
      best_worker=0
      for ((w=0; w<NUM_WORKERS; w++)); do
        if [ "${worker_task_count[$w]}" -lt "$min_count" ]; then
          min_count=${worker_task_count[$w]}
          best_worker=$w
        fi
      done
      task_assignment[$task]=$best_worker
      worker_task_count[$best_worker]=$((worker_task_count[$best_worker] + 1))
      continue
    fi

    # Count file overlap per worker
    declare -A overlap_count
    for ((w=0; w<NUM_WORKERS; w++)); do
      overlap_count[$w]=0
    done

    has_any_overlap=0
    for f in $files; do
      if [ -n "${file_owner[$f]+x}" ]; then
        owner=${file_owner[$f]}
        # Hotspot files get 2x weight to strongly prefer keeping them on one worker
        weight=1
        [ -n "${hotspot_files[$f]+x}" ] && weight=2
        overlap_count[$owner]=$((overlap_count[$owner] + weight))
        has_any_overlap=1
      fi
    done

    if [ "$has_any_overlap" -eq 1 ]; then
      # Assign to worker with most file overlap; ties broken by fewest tasks
      best_worker=0
      best_overlap=0
      best_count=999999
      for ((w=0; w<NUM_WORKERS; w++)); do
        ov=${overlap_count[$w]}
        tc=${worker_task_count[$w]}
        if [ "$ov" -gt "$best_overlap" ] || { [ "$ov" -eq "$best_overlap" ] && [ "$tc" -lt "$best_count" ]; }; then
          best_overlap=$ov
          best_worker=$w
          best_count=$tc
        fi
      done
    else
      # No overlap — assign to worker with fewest tasks
      best_worker=0
      min_count=999999
      for ((w=0; w<NUM_WORKERS; w++)); do
        if [ "${worker_task_count[$w]}" -lt "$min_count" ]; then
          min_count=${worker_task_count[$w]}
          best_worker=$w
        fi
      done
    fi

    # Assign task and register file ownership
    task_assignment[$task]=$best_worker
    worker_task_count[$best_worker]=$((worker_task_count[$best_worker] + 1))
    for f in $files; do
      if [ -z "${file_owner[$f]+x}" ]; then
        file_owner[$f]=$best_worker
        file_owner_count=$((file_owner_count + 1))
      fi
    done

    unset overlap_count
  done
done

# ── Build JSON output ───────────────────────────────────────────────────

echo "{"
echo "  \"workers\": {"

for ((w=0; w<NUM_WORKERS; w++)); do
  worker_tasks=""
  for task in "${incomplete_tasks[@]}"; do
    if [ "${task_assignment[$task]}" -eq "$w" ]; then
      [ -n "$worker_tasks" ] && worker_tasks+=", "
      worker_tasks+="$task"
    fi
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

# Output file ownership for debugging
echo "  \"file_owners\": {"
file_idx=0
file_count=$file_owner_count
for f in "${!file_owner[@]}"; do
  file_idx=$((file_idx + 1))
  comma=","
  [ "$file_idx" -eq "$file_count" ] && comma=""
  echo "    \"${f}\": \"worker-${file_owner[$f]}\"${comma}"
done
echo "  },"

echo "  \"total_incomplete\": ${#incomplete_tasks[@]},"
echo "  \"num_workers\": ${NUM_WORKERS}"
echo "}"
