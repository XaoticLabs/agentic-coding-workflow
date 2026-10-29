#!/bin/bash
# Project check runner — called by lint-on-stop.sh for any configured stack
# Expects: PROJECT_{LINT,TEST,VERIFY}_COMMAND resolved by caller
# Sets: has_code_errors, has_infra_warnings, infra_warnings, output (appends)

# Source infra classifier
SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
source "${SCRIPT_DIR}/infra-patterns.sh"

for action in lint test verify; do
  case "$action" in
    lint) command="$PROJECT_LINT_COMMAND" ;;
    test) command="$PROJECT_TEST_COMMAND" ;;
    verify) command="$PROJECT_VERIFY_COMMAND" ;;
  esac
  [ -n "$command" ] || continue
  output+="=== project ${action} ===\n"
  # Preserve project quoting and operators; pipe failures must not be hidden.
  command_output=$(bash -o pipefail -c "$command" 2>&1)
  command_exit=$?
  output+="$command_output\n\n"
  if [ "$command_exit" -eq 0 ]; then
    continue
  elif [ "$action" != lint ] && is_infra_failure "$command_output"; then
    has_infra_warnings=true
    infra_warnings+="${action} failed (infrastructure), "
  else
    has_code_errors=true
  fi
done
