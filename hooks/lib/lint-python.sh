#!/bin/bash
# Python lint/test runner — called by lint-on-stop.sh
# Expects: $CHANGED_FILES, $skip_tests, $infra_warnings set by caller
# Sets: has_code_errors, has_infra_warnings, infra_warnings, output (appends)

# Source infra classifier
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/infra-patterns.sh"

python_files=""
while IFS= read -r file; do
  [[ "$file" =~ \.py$ ]] && python_files="$python_files $file"
done <<< "$CHANGED_FILES"
python_files=$(echo "$python_files" | xargs)

if [ -z "$python_files" ]; then
  exit 0
fi

# Lint and type checks (no infrastructure needed)
output+="=== ruff format ===\n"
format_output=$(uv run ruff format $python_files 2>&1)
output+="$format_output\n\n"

output+="=== ruff check ===\n"
check_output=$(uv run ruff check $python_files 2>&1)
check_exit=$?
output+="$check_output\n\n"
if [ $check_exit -ne 0 ]; then
  has_code_errors=true
fi

output+="=== basedpyright ===\n"
pyright_output=$(uv run basedpyright $python_files 2>&1)
pyright_exit=$?
output+="$pyright_output\n\n"
if [ $pyright_exit -ne 0 ]; then
  has_code_errors=true
fi

# Tests — skip if infra probe already failed
if [ "$skip_tests" = true ]; then
  output+="=== pytest ===\nSkipped — infrastructure not available (${infra_warnings%%, })\n\n"
  return 0 2>/dev/null || exit 0
fi

# Find test files for changed files
test_files=""
while IFS= read -r file; do
  [[ ! "$file" =~ \.py$ ]] && continue

  if [[ "$file" =~ test_.*\.py$|.*_test\.py$|tests/.*\.py$ ]]; then
    test_files="$test_files $file"
  else
    dir=$(dirname "$file")
    basename_noext=$(basename "$file" .py)
    for pattern in "test_${basename_noext}.py" "${basename_noext}_test.py" "tests/test_${basename_noext}.py" "${dir}/test_${basename_noext}.py"; do
      if [ -f "$pattern" ]; then
        test_files="$test_files $pattern"
        break
      fi
    done
  fi
done <<< "$CHANGED_FILES"
test_files=$(echo "$test_files" | xargs | tr ' ' '\n' | sort -u | tr '\n' ' ')

if [ -z "$test_files" ]; then
  output+="=== pytest ===\nNo test files found for changed code\n\n"
  return 0 2>/dev/null || exit 0
fi

output+="=== pytest ===\n"
pytest_output=$(uv run pytest -q --tb=short $test_files 2>&1)
pytest_exit=$?
summary_line=$(echo "$pytest_output" | grep -E '(passed|failed|skipped|error)' | tail -1)
if [ $pytest_exit -ne 0 ]; then
  if is_infra_failure "$pytest_output"; then
    has_infra_warnings=true
    infra_warnings+="tests failed (infrastructure), "
    output+="$pytest_output\n\n"
  else
    output+="$pytest_output\n\n"
    has_code_errors=true
  fi
else
  output+="$summary_line\n\n"
fi
