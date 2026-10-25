#!/bin/bash
# Stop hook: Run linting, type checking, and tests - block Claude if code issues found
# Detects project type (Python/Elixir) and delegates to language-specific subscripts
#
# Smart behavior:
#   - Checks the entire project, including code committed before Stop
#   - Probes infrastructure (postgres, redis, docker) before running tests
#   - Blocks on real code errors (lint failures, type errors, test logic failures)
#   - Does NOT block on infrastructure failures (db down, docker missing, connection limits)

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/lib/common.sh"

input=$(read_hook_input)
echo "$input" | jq -e 'type == "object"' >/dev/null 2>&1 || exit 0
check_stop_hook_active "$input" && exit 0
cd_project
STATE_SCRIPT="${SCRIPT_DIR}/verification-state.py"

# Detect project type
if [ -f "mix.exs" ]; then
  PROJECT_TYPE="elixir"
elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
  PROJECT_TYPE="python"
else
  exit 0
fi

session_id=$(echo "$input" | jq -r '.session_id // "unknown"')
if ! before_state=$(python3 "$STATE_SCRIPT" snapshot); then
  python3 "$STATE_SCRIPT" record '{}' '{}' unavailable "$session_id" || true
  exit 0
fi
# A timeout or crash must not leave an earlier success looking current.
python3 "$STATE_SCRIPT" record "$before_state" '{}' running "$session_id" || true

# NUL-delimited paths and arrays preserve whitespace and shell metacharacters.
# Whole-project selection catches committed changes and config-only changes.
PROJECT_FILES=()
while IFS= read -r -d '' file; do
  [ -f "$file" ] && PROJECT_FILES+=("$file")
done < <(git ls-files --cached --others --exclude-standard -z)
output=""
has_code_errors=false
has_infra_warnings=false
infra_warnings=""
# Per-language skip flags — set by probe_infrastructure, consumed by each subscript
export SKIP_TESTS_PYTHON=false
export SKIP_TESTS_ELIXIR=false

# ── Infrastructure probes ────────────────────────────────────────────

probe_infrastructure() {
  local needs_postgres_python=false needs_postgres_elixir=false
  local needs_redis=false needs_docker=false

  # Determine per-language postgres needs independently
  if grep -q "postgrex\|ecto_sql\|postgres" mix.exs 2>/dev/null; then
    needs_postgres_elixir=true
  fi
  if grep -qi "psycopg\|asyncpg\|sqlalchemy\|django.db\|postgres" pyproject.toml setup.py requirements*.txt 2>/dev/null; then
    needs_postgres_python=true
  fi
  grep -q "redix\|redis" mix.exs 2>/dev/null && needs_redis=true
  grep -qi "redis\|celery" pyproject.toml setup.py requirements*.txt 2>/dev/null && needs_redis=true

  [ -f "docker-compose.yml" ] || [ -f "docker-compose.yaml" ] || [ -f "compose.yml" ] && needs_docker=true

  if command -v pg_isready &>/dev/null && ! pg_isready -q 2>/dev/null; then
    if [ "$needs_postgres_elixir" = true ]; then
      has_infra_warnings=true; infra_warnings+="postgres is not running, "; SKIP_TESTS_ELIXIR=true
    fi
    if [ "$needs_postgres_python" = true ]; then
      has_infra_warnings=true; infra_warnings+="postgres is not running, "; SKIP_TESTS_PYTHON=true
    fi
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

if ! after_state=$(python3 "$STATE_SCRIPT" snapshot); then
  python3 "$STATE_SCRIPT" record "$before_state" '{}' unavailable "$session_id" || true
  exit 0
fi
status=passed
if [ "$has_infra_warnings" = true ]; then status=incomplete; fi
if [ "$has_code_errors" = true ]; then status=failed; fi
if [ "$before_state" != "$after_state" ]; then
  has_code_errors=true
  status=changed
  output+="Verification inputs changed while checks ran. Run formatting separately, then verify again.\n"
fi
python3 "$STATE_SCRIPT" record "$before_state" "$after_state" "$status" "$session_id" || true

if [ "$has_code_errors" = true ]; then
  if [ "$has_infra_warnings" = true ]; then
    output+="\nNote: Some failures are infrastructure-related (${infra_warnings%%, }). Ignore those — focus only on code errors above.\n"
  fi
  reason=$(echo -e "$output" | head -200 | jq -Rs .)
  echo "{\"decision\": \"block\", \"reason\": $reason}"
  exit 0
fi

if [ "$has_infra_warnings" = true ]; then
  message="Tests could not run fully (${infra_warnings%%, }). Verification is incomplete; re-run when infrastructure is available."
  jq -n --arg message "$message" '{systemMessage: $message}'
  exit 0
fi

exit 0
