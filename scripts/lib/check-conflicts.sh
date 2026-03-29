#!/usr/bin/env bash
# Check for merge conflicts between branch pairs using git merge-tree.
# This is a read-only check — no repository state is modified.
#
# Usage: check-conflicts.sh <base-branch> <branch1> <branch2> [branch3 ...]
# Output: JSON with conflict status per branch pair
#
# Exit codes:
#   0 = no conflicts detected
#   1 = conflicts detected (details in JSON output)
#   2 = usage error

set -euo pipefail

BASE="${1:?Usage: check-conflicts.sh <base-branch> <branch1> <branch2> ...}"
shift
BRANCHES=("$@")

if [ ${#BRANCHES[@]} -lt 2 ]; then
  echo '{"error": "Need at least 2 branches to check conflicts"}' >&2
  exit 2
fi

HAS_CONFLICTS=false

echo "{"
echo '  "base": "'"$BASE"'",'
echo '  "conflicts": ['

first=true
for ((i=0; i<${#BRANCHES[@]}; i++)); do
  for ((j=i+1; j<${#BRANCHES[@]}; j++)); do
    branch_a="${BRANCHES[$i]}"
    branch_b="${BRANCHES[$j]}"

    # git merge-tree performs a three-way merge in memory
    # Exit code 0 = clean merge, non-zero = conflicts
    MERGE_OUTPUT=$(git merge-tree --write-tree "$BASE" "$branch_a" "$branch_b" 2>&1) && merge_clean=true || merge_clean=false

    if [ "$merge_clean" = false ]; then
      # Extract conflicted file names from merge-tree output
      conflicted_files=$(echo "$MERGE_OUTPUT" | grep -E '^CONFLICT' | sed 's/CONFLICT ([^)]*): //' | head -10 | tr '\n' ',' | sed 's/,$//')

      if [ "$first" = true ]; then first=false; else echo ","; fi
      printf '    {"branch_a": "%s", "branch_b": "%s", "has_conflict": true, "files": "%s"}' \
        "$branch_a" "$branch_b" "$conflicted_files"
      HAS_CONFLICTS=true
    fi
  done
done

echo ""
echo "  ],"
echo '  "has_any_conflicts": '"$HAS_CONFLICTS"
echo "}"

if [ "$HAS_CONFLICTS" = true ]; then
  exit 1
else
  exit 0
fi
