#!/usr/bin/env bash
# Explicit, mutating formatting. Stop hooks only verify formatting.
set -euo pipefail
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_DIR="${1:-${CLAUDE_PROJECT_DIR:-.}}"
PROJECT_DIR=$(realpath "$PROJECT_DIR")
if command=$(python3 "${SCRIPT_DIR}/project-commands.py" get "$PROJECT_DIR" format); then
  : # An empty/null override explicitly disables formatting.
else
  status=$?
  [ "$status" -eq 1 ] || exit "$status"
  command=""
  if [ -f "${PROJECT_DIR}/mix.exs" ]; then
    command="mix format"
  fi
fi
cd "$PROJECT_DIR"
if [ -n "$command" ]; then exec bash -o pipefail -c "$command"; fi
