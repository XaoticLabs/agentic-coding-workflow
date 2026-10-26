#!/bin/bash
# Project lint/test runner — called by lint-on-stop.sh for any configured stack
# Expects: PROJECT_LINT_COMMAND and PROJECT_TEST_COMMAND resolved by caller
# Sets: has_code_errors, has_infra_warnings, infra_warnings, output (appends)

# Source infra classifier
SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
source "${SCRIPT_DIR}/infra-patterns.sh"

for action in lint test; do
  if [ "$action" = lint ]; then command="$PROJECT_LINT_COMMAND"; else command="$PROJECT_TEST_COMMAND"; fi
  [ -n "$command" ] || continue
  output+="=== project ${action} ===\n"
  # Preserve project quoting and operators; pipe failures must not be hidden.
  command_output=$(bash -o pipefail -c "$command" 2>&1)
  command_exit=$?
  output+="$command_output\n\n"
  if [ "$command_exit" -eq 0 ]; then
    continue
  elif [ "$action" = test ] && is_infra_failure "$command_output"; then
    has_infra_warnings=true
    infra_warnings+="tests failed (infrastructure), "
  else
    has_code_errors=true
  fi
done
