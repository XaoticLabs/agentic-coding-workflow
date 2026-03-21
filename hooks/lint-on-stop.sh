#!/bin/bash
# Stop hook: Run linting, type checking, and tests - block Claude if issues found
# Detects project type (Python/Elixir) and runs appropriate commands
# Only checks files that have been modified on the current branch

# Read stdin to get hook input
input=$(cat)

# Check if stop_hook_active to prevent infinite loops
stop_hook_active=$(echo "$input" | jq -r '.stop_hook_active // false')
if [ "$stop_hook_active" = "true" ]; then
    # Already ran once, let Claude stop to avoid infinite loop
    exit 0
fi

# Change to project directory
cd "$CLAUDE_PROJECT_DIR" || exit 0

# Detect project type
detect_project_type() {
    if [ -f "mix.exs" ]; then
        echo "elixir"
    elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
        echo "python"
    else
        echo "unknown"
    fi
}

PROJECT_TYPE=$(detect_project_type)

# Get staged and unstaged changes only
CHANGED_FILES=$(git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null)

# Remove duplicates and empty lines, filter to only existing files
CHANGED_FILES=$(echo "$CHANGED_FILES" | sort -u | grep -v '^$' | while read -r f; do [ -f "$f" ] && echo "$f"; done)

if [ -z "$CHANGED_FILES" ]; then
    # No changes - skip checks
    exit 0
fi

# Collect all output and track failures
output=""
has_errors=false

run_python_checks() {
    # Filter to only Python files
    local python_files=""
    while IFS= read -r file; do
        [[ "$file" =~ \.py$ ]] && python_files="$python_files $file"
    done <<< "$CHANGED_FILES"
    python_files=$(echo "$python_files" | xargs)  # trim whitespace

    if [ -z "$python_files" ]; then
        # No Python files changed
        exit 0
    fi

    # Run ruff format on changed files
    output+="=== ruff format ===\n"
    format_output=$(uv run ruff format $python_files 2>&1)
    format_exit=$?
    output+="$format_output\n\n"

    # Run ruff check on changed files
    output+="=== ruff check ===\n"
    check_output=$(uv run ruff check $python_files 2>&1)
    check_exit=$?
    output+="$check_output\n\n"
    if [ $check_exit -ne 0 ]; then
        has_errors=true
    fi

    # Run basedpyright on changed files
    output+="=== basedpyright ===\n"
    pyright_output=$(uv run basedpyright $python_files 2>&1)
    pyright_exit=$?
    output+="$pyright_output\n\n"
    if [ $pyright_exit -ne 0 ]; then
        has_errors=true
    fi

    # Find test files for changed files
    local test_files=""
    while IFS= read -r file; do
        [[ ! "$file" =~ \.py$ ]] && continue

        if [[ "$file" =~ test_.*\.py$|.*_test\.py$|tests/.*\.py$ ]]; then
            # File is already a test file
            test_files="$test_files $file"
        else
            # Look for corresponding test file
            local dir=$(dirname "$file")
            local basename=$(basename "$file" .py)
            for pattern in "test_${basename}.py" "${basename}_test.py" "tests/test_${basename}.py" "${dir}/test_${basename}.py"; do
                if [ -f "$pattern" ]; then
                    test_files="$test_files $pattern"
                    break
                fi
            done
        fi
    done <<< "$CHANGED_FILES"
    test_files=$(echo "$test_files" | xargs | tr ' ' '\n' | sort -u | tr '\n' ' ')  # dedupe

    if [ -z "$test_files" ]; then
        output+="=== pytest ===\nNo test files found for changed code\n\n"
        return
    fi

    # Run pytest on relevant test files
    output+="=== pytest ===\n"
    pytest_output=$(uv run pytest -q --tb=line $test_files 2>&1)
    pytest_exit=$?
    # Extract just the summary line (last non-empty line with passed/failed/skipped)
    summary_line=$(echo "$pytest_output" | grep -E '(passed|failed|skipped|error)' | tail -1)
    if [ $pytest_exit -ne 0 ]; then
        # Show failures and summary
        output+="$pytest_output\n\n"
        has_errors=true
    else
        # Just show summary line
        output+="$summary_line\n\n"
    fi
}

run_elixir_checks() {
    # Filter to only Elixir files
    local elixir_files=""
    while IFS= read -r file; do
        [[ "$file" =~ \.exs?$ ]] && elixir_files="$elixir_files $file"
    done <<< "$CHANGED_FILES"
    elixir_files=$(echo "$elixir_files" | xargs)  # trim whitespace

    if [ -z "$elixir_files" ]; then
        # No Elixir files changed
        exit 0
    fi

    # Run mix format on changed files
    output+="=== mix format ===\n"
    format_output=$(mix format $elixir_files 2>&1)
    format_exit=$?
    output+="$format_output\n\n"

    # Find test files for changed files
    local test_files=""
    while IFS= read -r file; do
        [[ ! "$file" =~ \.exs?$ ]] && continue

        if [[ "$file" =~ _test\.exs$ ]]; then
            # File is already a test file
            test_files="$test_files $file"
        elif [[ "$file" =~ ^lib/(.*)\.ex$ ]]; then
            # Look for corresponding test file
            local base_path="${BASH_REMATCH[1]}"
            local test_file="test/${base_path}_test.exs"
            if [ -f "$test_file" ]; then
                test_files="$test_files $test_file"
            fi
        fi
    done <<< "$CHANGED_FILES"
    test_files=$(echo "$test_files" | xargs | tr ' ' '\n' | sort -u | tr '\n' ' ')  # dedupe

    if [ -z "$test_files" ]; then
        output+="=== mix test ===\nNo test files found for changed code\n\n"
        return
    fi

    # Run mix test on relevant test files
    output+="=== mix test ===\n"
    test_output=$(mix test --warnings-as-errors $test_files 2>&1)
    test_exit=$?
    # Extract just the summary line
    summary_line=$(echo "$test_output" | grep -E '(test|failure|error|passed)' | tail -1)
    if [ $test_exit -ne 0 ]; then
        # Show failures and summary
        output+="$test_output\n\n"
        has_errors=true
    else
        # Just show summary line
        output+="$summary_line\n\n"
    fi
}

# Run checks based on project type
case "$PROJECT_TYPE" in
    "python")
        run_python_checks
        ;;
    "elixir")
        run_elixir_checks
        ;;
    *)
        # Unknown project type, skip checks
        exit 0
        ;;
esac

# If there are errors, block Claude from stopping and ask it to fix them
if [ "$has_errors" = true ]; then
    # Properly escape output for JSON using jq
    reason=$(echo -e "$output" | head -200 | jq -Rs .)
    echo "{\"decision\": \"block\", \"reason\": $reason}"
    exit 0
fi

# No errors, show summary and let Claude stop
echo -e "$output"
exit 0
