#!/bin/bash
# Stop hook: Run linting, type checking, and tests - block Claude if code issues found
# Detects project type (Python/Elixir) and delegates to language-specific subscripts
#
# Smart behavior:
#   - Skips on main/master/develop/release branches (nothing to gate)
#   - Probes infrastructure (postgres, redis, docker) before running tests
#   - Blocks on real code errors (lint failures, type errors, test logic failures)
#   - Does NOT block on infrastructure failures (db down, docker missing, connection limits)

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/lib/common.sh"

input=$(read_hook_input)
check_stop_hook_active "$input" && exit 0
cd_project

# Skip on main/master/develop/release — these branches don't need stop-gating
current_branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
case "$current_branch" in
  main|master|develop|release|release/*) exit 0 ;;
esac

# Detect project type
if [ -f "mix.exs" ]; then
  PROJECT_TYPE="elixir"
elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
  PROJECT_TYPE="python"
else
  exit 0
fi

# Get staged and unstaged changes, deduplicate, filter to existing files
CHANGED_FILES=$(git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null)
CHANGED_FILES=$(echo "$CHANGED_FILES" | sort -u | grep -v '^$' | while read -r f; do [ -f "$f" ] && echo "$f"; done)

if [ -z "$CHANGED_FILES" ]; then
  exit 0
fi

# Shared state for subscripts
export CHANGED_FILES
output=""
has_code_errors=false
has_infra_warnings=false
infra_warnings=""
skip_tests=false

# ── Infrastructure probes ────────────────────────────────────────────

probe_infrastructure() {
  local needs_postgres=false needs_redis=false needs_docker=false

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

  [ -f "docker-compose.yml" ] || [ -f "docker-compose.yaml" ] || [ -f "compose.yml" ] && needs_docker=true

  if [ "$needs_postgres" = true ] && command -v pg_isready &>/dev/null && ! pg_isready -q 2>/dev/null; then
    has_infra_warnings=true; infra_warnings+="postgres is not running, "; skip_tests=true
  fi
  if [ "$needs_redis" = true ] && command -v redis-cli &>/dev/null && ! redis-cli ping &>/dev/null; then
    has_infra_warnings=true; infra_warnings+="redis is not running, "
  fi
  if [ "$needs_docker" = true ] && command -v docker &>/dev/null && ! docker info &>/dev/null 2>&1; then
    has_infra_warnings=true; infra_warnings+="docker is not running, "
  fi
}

probe_infrastructure

# ── Delegate to language-specific runner ─────────────────────────────

case "$PROJECT_TYPE" in
  python)  source "${SCRIPT_DIR}/lib/lint-python.sh" ;;
  elixir)  source "${SCRIPT_DIR}/lib/lint-elixir.sh" ;;
esac

# ── Report results ───────────────────────────────────────────────────

if [ "$has_code_errors" = true ]; then
  if [ "$has_infra_warnings" = true ]; then
    output+="\nNote: Some failures are infrastructure-related (${infra_warnings%%, }). Ignore those — focus only on code errors above.\n"
  fi
  reason=$(echo -e "$output" | head -200 | jq -Rs .)
  echo "{\"decision\": \"block\", \"reason\": $reason}"
  exit 0
fi

if [ "$has_infra_warnings" = true ]; then
  echo -e "$output"
  echo ""
  echo "Note: Tests could not run fully (${infra_warnings%%, }). Lint/type checks passed. Re-run tests once infrastructure is available."
  exit 0
fi

echo -e "$output"
exit 0
