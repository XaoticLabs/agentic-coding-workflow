#!/bin/bash
# Elixir lint/test runner — called by lint-on-stop.sh
# Expects: PROJECT_FILES array and infrastructure state set by caller
# Sets: has_code_errors, has_infra_warnings, infra_warnings, output (appends)

# Source infra classifier
SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
source "${SCRIPT_DIR}/infra-patterns.sh"

elixir_files=()
for file in "${PROJECT_FILES[@]}"; do
  [[ "$file" =~ \.exs?$ ]] && elixir_files+=("$file")
done

if [ ${#elixir_files[@]} -eq 0 ]; then
  return 0
fi

# Format check (no infrastructure needed)
output+="=== mix format --check-formatted ===\n"
format_output=$(mix format --check-formatted "${elixir_files[@]}" 2>&1)
format_exit=$?
output+="$format_output\n\n"
if [ $format_exit -ne 0 ]; then has_code_errors=true; fi

# Tests — skip if Elixir-specific infra probe failed
if [ "${SKIP_TESTS_ELIXIR:-false}" = true ]; then
  output+="=== mix test ===\nSkipped — infrastructure not available (${infra_warnings%%, })\n\n"
  return 0 2>/dev/null || exit 0
fi

output+="=== mix test ===\n"
test_output=$(mix test --warnings-as-errors 2>&1)
test_exit=$?
summary_line=$(echo "$test_output" | grep -E '(test|failure|error|passed)' | tail -1)
if [ $test_exit -ne 0 ]; then
  if is_infra_failure "$test_output"; then
    has_infra_warnings=true
    infra_warnings+="tests failed (infrastructure), "
    output+="$test_output\n\n"
  else
    output+="$test_output\n\n"
    has_code_errors=true
  fi
else
  output+="$summary_line\n\n"
fi
