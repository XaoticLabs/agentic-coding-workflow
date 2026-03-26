#!/usr/bin/env bash
# Analyze file overlap between worker branches to determine optimal merge order.
#
# Usage: analyze-overlap.sh <parent-branch> <branch1> <branch2> [branch3 ...]
#
# Output: JSON with changed files per branch, overlap matrix, and recommended merge order.
# Strategy: merge the branch with the fewest changed files first, then greedily pick
# the branch with the least overlap against already-merged files.

set -euo pipefail

PARENT="${1:?Usage: analyze-overlap.sh <parent-branch> <branch1> <branch2> ...}"
shift
BRANCHES=("$@")

if [ ${#BRANCHES[@]} -eq 0 ]; then
  echo '{"error": "No branches provided"}' >&2
  exit 1
fi

# Collect changed files per branch
declare -A BRANCH_FILES
declare -A BRANCH_COUNTS

for branch in "${BRANCHES[@]}"; do
  files=$(git diff --name-only "${PARENT}...${branch}" 2>/dev/null | sort)
  BRANCH_FILES["$branch"]="$files"
  count=$(echo "$files" | grep -c '.' || echo "0")
  BRANCH_COUNTS["$branch"]="$count"
done

# Build overlap data: for each pair, count shared files
# Output as JSON
echo "{"

# Per-branch info
echo '  "branches": ['
first=true
for branch in "${BRANCHES[@]}"; do
  count="${BRANCH_COUNTS[$branch]}"
  commits=$(git rev-list --count "${PARENT}..${branch}" 2>/dev/null || echo "0")
  if [ "$first" = true ]; then first=false; else echo ","; fi
  printf '    {"name": "%s", "files_changed": %s, "commits": %s}' "$branch" "$count" "$commits"
done
echo ""
echo "  ],"

# Overlap matrix
echo '  "overlaps": ['
first_i=true
for i in "${BRANCHES[@]}"; do
  for j in "${BRANCHES[@]}"; do
    [ "$i" \< "$j" ] || [ "$i" = "$j" ] && continue 2>/dev/null || true
    # Only compare pairs where i < j lexically to avoid dupes
    if [[ "$i" > "$j" ]] || [[ "$i" == "$j" ]]; then
      continue
    fi
    shared=$(comm -12 <(echo "${BRANCH_FILES[$i]}") <(echo "${BRANCH_FILES[$j]}") | grep -c '.' || echo "0")
    if [ "$shared" -gt 0 ]; then
      if [ "$first_i" = true ]; then first_i=false; else echo ","; fi
      shared_files=$(comm -12 <(echo "${BRANCH_FILES[$i]}") <(echo "${BRANCH_FILES[$j]}") | head -10 | jq -R . | jq -s .)
      printf '    {"branch_a": "%s", "branch_b": "%s", "shared_files": %s, "count": %s}' "$i" "$j" "$shared_files" "$shared"
    fi
  done
done
echo ""
echo "  ],"

# Recommended merge order: greedy — fewest files first, then least overlap with merged set
echo '  "recommended_order": ['
merged_files=""
remaining=("${BRANCHES[@]}")
first=true

while [ ${#remaining[@]} -gt 0 ]; do
  best=""
  best_score=999999
  best_idx=0

  for idx in "${!remaining[@]}"; do
    branch="${remaining[$idx]}"
    files="${BRANCH_FILES[$branch]}"
    count="${BRANCH_COUNTS[$branch]}"

    # Calculate overlap with already-merged files
    if [ -z "$merged_files" ]; then
      overlap=0
    else
      overlap=$(comm -12 <(echo "$files") <(echo "$merged_files") | grep -c '.' || echo "0")
    fi

    # Score = overlap * 10 + file count (prefer low overlap, break ties by fewer files)
    score=$((overlap * 10 + count))

    if [ "$score" -lt "$best_score" ]; then
      best="$branch"
      best_score="$score"
      best_idx="$idx"
    fi
  done

  if [ "$first" = true ]; then first=false; else echo ","; fi
  printf '    "%s"' "$best"

  # Add this branch's files to the merged set
  if [ -z "$merged_files" ]; then
    merged_files="${BRANCH_FILES[$best]}"
  else
    merged_files=$(printf '%s\n%s' "$merged_files" "${BRANCH_FILES[$best]}" | sort -u)
  fi

  # Remove from remaining
  unset 'remaining[$best_idx]'
  remaining=("${remaining[@]}")
done
echo ""
echo "  ]"
echo "}"
