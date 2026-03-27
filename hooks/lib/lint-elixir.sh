#!/bin/bash
# Elixir lint/test runner — called by lint-on-stop.sh
# Expects: $CHANGED_FILES, $skip_tests, $infra_warnings set by caller
# Sets: has_code_errors, has_infra_warnings, infra_warnings, output (appends)

# Source infra classifier
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/infra-patterns.sh"

elixir_files=""
while IFS= read -r file; do
  [[ "$file" =~ \.exs?$ ]] && elixir_files="$elixir_files $file"
done <<< "$CHANGED_FILES"
elixir_files=$(echo "$elixir_files" | xargs)

if [ -z "$elixir_files" ]; then
  exit 0
fi

# Format check (no infrastructure needed)
output+="=== mix format ===\n"
format_output=$(mix format $elixir_files 2>&1)
output+="$format_output\n\n"

# Tests — skip if infra probe already failed
if [ "$skip_tests" = true ]; then
  output+="=== mix test ===\nSkipped — infrastructure not available (${infra_warnings%%, })\n\n"
  return 0 2>/dev/null || exit 0
fi

# Find test files for changed files
test_files=""
while IFS= read -r file; do
  [[ ! "$file" =~ \.exs?$ ]] && continue

  if [[ "$file" =~ _test\.exs$ ]]; then
    test_files="$test_files $file"
  elif [[ "$file" =~ ^lib/(.*)\.ex$ ]]; then
    base_path="${BASH_REMATCH[1]}"
    test_file="test/${base_path}_test.exs"
    if [ -f "$test_file" ]; then
      test_files="$test_files $test_file"
    fi
  fi
done <<< "$CHANGED_FILES"
test_files=$(echo "$test_files" | xargs | tr ' ' '\n' | sort -u | tr '\n' ' ')

if [ -z "$test_files" ]; then
  output+="=== mix test ===\nNo test files found for changed code\n\n"
  return 0 2>/dev/null || exit 0
fi

output+="=== mix test ===\n"
test_output=$(mix test --warnings-as-errors $test_files 2>&1)
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
