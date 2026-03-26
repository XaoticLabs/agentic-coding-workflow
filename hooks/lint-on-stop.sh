#!/bin/bash
# Stop hook: Run linting, type checking, and tests - block Claude if code issues found
# Detects project type (Python/Elixir) and runs appropriate commands
# Only checks files that have been modified on the current branch
#
# Smart behavior:
#   - Skips on main/master/develop/release branches (nothing to gate)
#   - Probes infrastructure (postgres, redis, docker) before running tests
#   - Blocks on real code errors (lint failures, type errors, test logic failures)
#   - Does NOT block on infrastructure failures (db down, docker missing, connection limits)
#     — reports them as warnings so Claude doesn't try to "fix" your infra

# Read stdin to get hook input
input=$(cat)

# Check if stop_hook_active to prevent infinite loops
stop_hook_active=$(echo "$input" | jq -r '.stop_hook_active // false')
if [ "$stop_hook_active" = "true" ]; then
    exit 0
fi

# Change to project directory
cd "$CLAUDE_PROJECT_DIR" || exit 0

# Skip on main/master/develop/release — these branches don't need stop-gating
current_branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
case "$current_branch" in
    main|master|develop|release|release/*) exit 0 ;;
esac

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
    exit 0
fi

# Collect all output and track failures
output=""
has_code_errors=false
has_infra_warnings=false
infra_warnings=""
skip_tests=false

# ---------------------------------------------------------------------------
# Infrastructure probes — check before running tests, not after
# ---------------------------------------------------------------------------
probe_infrastructure() {
    local needs_postgres=false
    local needs_redis=false
    local needs_docker=false

    # Detect what services this project likely needs
    case "$PROJECT_TYPE" in
        elixir)
            grep -q "postgrex\|ecto_sql\|postgres" mix.exs 2>/dev/null && needs_postgres=true
            grep -q "redix\|redis" mix.exs 2>/dev/null && needs_redis=true
            ;;
        python)
            grep -qi "psycopg\|asyncpg\|sqlalchemy\|django.db\|postgres" pyproject.toml setup.py requirements*.txt 2>/dev/null && needs_postgres=true
            grep -qi "redis\|celery" pyproject.toml setup.py requirements*.txt 2>/dev/null && needs_redis=true
            ;;
    esac

    # Check for docker-compose usage
    [ -f "docker-compose.yml" ] || [ -f "docker-compose.yaml" ] || [ -f "compose.yml" ] && needs_docker=true

    # Probe postgres
    if [ "$needs_postgres" = true ]; then
        if command -v pg_isready &>/dev/null; then
            if ! pg_isready -q 2>/dev/null; then
                has_infra_warnings=true
                infra_warnings+="postgres is not running, "
                skip_tests=true
            fi
        fi
    fi

    # Probe redis
    if [ "$needs_redis" = true ]; then
        if command -v redis-cli &>/dev/null; then
            if ! redis-cli ping &>/dev/null; then
                has_infra_warnings=true
                infra_warnings+="redis is not running, "
            fi
        fi
    fi

    # Probe docker
    if [ "$needs_docker" = true ]; then
        if command -v docker &>/dev/null; then
            if ! docker info &>/dev/null 2>&1; then
                has_infra_warnings=true
                infra_warnings+="docker is not running, "
            fi
        fi
    fi
}

# ---------------------------------------------------------------------------
# Fallback: classify test output as infra vs code failure
# Tight list — only patterns that are NEVER caused by code bugs
# ---------------------------------------------------------------------------
INFRA_PATTERNS=(
    # Connection failures
    "connection refused"
    "econnrefused"
    "ECONNREFUSED"
    "tcp connect.*refused"
    "ETIMEDOUT"

    # Postgres-specific
    "Postgrex.Error.*too_many_connections"
    "too many connections"
    "too many clients already"
    "53300"
    "remaining connection slots"
    "database.*does not exist"

    # Docker
    "Cannot connect to the Docker daemon"

    # General DB connectivity
    "DBConnection.ConnectionError"
    "OperationalError.*Connection refused"
    "could not connect to server"
)

is_infra_failure() {
    local test_output="$1"
    for pattern in "${INFRA_PATTERNS[@]}"; do
        if echo "$test_output" | grep -qi "$pattern"; then
            return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Language-specific check runners
# ---------------------------------------------------------------------------
run_python_checks() {
    local python_files=""
    while IFS= read -r file; do
        [[ "$file" =~ \.py$ ]] && python_files="$python_files $file"
    done <<< "$CHANGED_FILES"
    python_files=$(echo "$python_files" | xargs)

    if [ -z "$python_files" ]; then
        exit 0
    fi

    # Lint and type checks (these don't need infrastructure)
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
        return
    fi

    # Find test files for changed files
    local test_files=""
    while IFS= read -r file; do
        [[ ! "$file" =~ \.py$ ]] && continue

        if [[ "$file" =~ test_.*\.py$|.*_test\.py$|tests/.*\.py$ ]]; then
            test_files="$test_files $file"
        else
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
    test_files=$(echo "$test_files" | xargs | tr ' ' '\n' | sort -u | tr '\n' ' ')

    if [ -z "$test_files" ]; then
        output+="=== pytest ===\nNo test files found for changed code\n\n"
        return
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
}

run_elixir_checks() {
    local elixir_files=""
    while IFS= read -r file; do
        [[ "$file" =~ \.exs?$ ]] && elixir_files="$elixir_files $file"
    done <<< "$CHANGED_FILES"
    elixir_files=$(echo "$elixir_files" | xargs)

    if [ -z "$elixir_files" ]; then
        exit 0
    fi

    # Format check (doesn't need infrastructure)
    output+="=== mix format ===\n"
    format_output=$(mix format $elixir_files 2>&1)
    output+="$format_output\n\n"

    # Tests — skip if infra probe already failed
    if [ "$skip_tests" = true ]; then
        output+="=== mix test ===\nSkipped — infrastructure not available (${infra_warnings%%, })\n\n"
        return
    fi

    # Find test files for changed files
    local test_files=""
    while IFS= read -r file; do
        [[ ! "$file" =~ \.exs?$ ]] && continue

        if [[ "$file" =~ _test\.exs$ ]]; then
            test_files="$test_files $file"
        elif [[ "$file" =~ ^lib/(.*)\.ex$ ]]; then
            local base_path="${BASH_REMATCH[1]}"
            local test_file="test/${base_path}_test.exs"
            if [ -f "$test_file" ]; then
                test_files="$test_files $test_file"
            fi
        fi
    done <<< "$CHANGED_FILES"
    test_files=$(echo "$test_files" | xargs | tr ' ' '\n' | sort -u | tr '\n' ' ')

    if [ -z "$test_files" ]; then
        output+="=== mix test ===\nNo test files found for changed code\n\n"
        return
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
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Probe infrastructure before running anything
probe_infrastructure

# Run checks based on project type
case "$PROJECT_TYPE" in
    "python")
        run_python_checks
        ;;
    "elixir")
        run_elixir_checks
        ;;
    *)
        exit 0
        ;;
esac

# Real code errors — block Claude, ask it to fix
if [ "$has_code_errors" = true ]; then
    if [ "$has_infra_warnings" = true ]; then
        output+="\nNote: Some failures are infrastructure-related (${infra_warnings%%, }). Ignore those — focus only on code errors above.\n"
    fi
    reason=$(echo -e "$output" | head -200 | jq -Rs .)
    echo "{\"decision\": \"block\", \"reason\": $reason}"
    exit 0
fi

# Only infra failures, no code errors — warn but don't block
if [ "$has_infra_warnings" = true ]; then
    echo -e "$output"
    echo ""
    echo "Note: Tests could not run fully (${infra_warnings%%, }). Lint/type checks passed. Re-run tests once infrastructure is available."
    exit 0
fi

# Clean — show summary and let Claude stop
echo -e "$output"
exit 0
