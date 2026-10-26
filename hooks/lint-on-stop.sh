#!/bin/bash
# Stop hook: Run linting, type checking, and tests - block Claude if code issues found
# Runs project-owned commands for any configured stack, with a legacy Elixir path
#
# Smart behavior:
#   - Checks the entire project, including code committed before Stop
#   - Probes infrastructure (postgres, redis, docker) before running tests
#   - Blocks on real code errors (lint failures, type errors, test logic failures)
#   - Reports infrastructure/unconfigured checks as incomplete, with bounded retries

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/lib/common.sh"

input=$(read_hook_input)
echo "$input" | jq -e 'type == "object"' >/dev/null 2>&1 || exit 0
cd_project "$input"
STATE_SCRIPT="${SCRIPT_DIR}/verification-state.py"

# A marker identifies a stack, never its package manager or verification policy.
# Explicit commands also support mixed projects and roots without language markers.
COMMANDS_SCRIPT="${SCRIPT_DIR}/../scripts/project-commands.py"
readiness=$(python3 "$COMMANDS_SCRIPT" readiness "$PWD" 2>/dev/null)
config_status=$?
if [ "$config_status" -gt 1 ]; then
  reason=$(printf '%s' "$readiness" | jq -r '(.configuration // "project commands") + ": " + (.error // "readiness unavailable")' 2>/dev/null)
  jq -n --arg reason "${reason:-Project readiness could not be read; verification is unavailable.}" '{decision: "block", reason: $reason}'
  exit 0
fi
readiness_status=$(printf '%s' "$readiness" | jq -r '.status')
case "$readiness_status" in
  not_applicable) exit 0 ;;
  legacy_elixir) PROJECT_TYPE="elixir" ;;
  configured|unconfigured|disabled) PROJECT_TYPE="configured" ;;
  *) jq -n '{decision: "block", reason: "Project readiness returned an invalid result; verification is unavailable."}'; exit 0 ;;
esac
PROJECT_LINT_COMMAND=$(printf '%s' "$readiness" | jq -r '.checks.lint.command // ""')
PROJECT_TEST_COMMAND=$(printf '%s' "$readiness" | jq -r '.checks.test.command // ""')

session_id=$(echo "$input" | jq -r '.session_id // "unknown"')
verification_blocked() {
  jq -n --arg message "$1" '{continue: false, stopReason: $message, systemMessage: $message}'
}
if ! before_state=$(python3 "$STATE_SCRIPT" snapshot); then
  python3 "$STATE_SCRIPT" record '{}' '{}' unavailable "$session_id" || true
  verification_blocked "Verification is unavailable. Completion is blocked until source state can be read."
  exit 0
fi
# Retry correction turns, with a session-local bound. Reuse success only for
# exactly the same revision and working inputs, including ignored guidance.
active=$(echo "$input" | jq -r '.stop_hook_active // false')
if ! attempt=$(python3 "$STATE_SCRIPT" attempt "$before_state" "$session_id" "$active"); then
  verification_blocked "Verification state could not be recorded. Completion is blocked."
  exit 0
fi
case "$(echo "$attempt" | jq -r '.action')" in
  passed) exit 0 ;;
  blocked)
    verification_blocked "Verification remains blocked after three attempts. Report the failing checks and request human intervention; completion has not been verified."
    exit 0 ;;
esac

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
has_missing_checks=false
if [ "$readiness_status" = unconfigured ]; then
  missing_checks=$(printf '%s' "$readiness" | jq -r '[.checks | to_entries[] | select(.value.status == "unconfigured") | .key] | join(", ")')
  has_missing_checks=true
  output+="Unconfigured checks: ${missing_checks}. Select existing CI/task commands in .claude/project-commands.json; null or an empty string explicitly disables an action. Do not invent tooling or disable an unknown check to get a pass.\n"
fi
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

# Configured project commands own their environment and infrastructure needs.
[ "$PROJECT_TYPE" != elixir ] || probe_infrastructure

# ── Delegate to language-specific runner ─────────────────────────────

case "$PROJECT_TYPE" in
  configured) source "${SCRIPT_DIR}/lib/lint-project.sh" ;;
  elixir)  source "${SCRIPT_DIR}/lib/lint-elixir.sh" ;;
esac

# ── Report results ───────────────────────────────────────────────────

if ! after_state=$(python3 "$STATE_SCRIPT" snapshot); then
  python3 "$STATE_SCRIPT" record "$before_state" '{}' unavailable "$session_id" || true
  verification_blocked "Verification state became unavailable. Completion has not been verified."
  exit 0
fi
status=passed
if [ "$readiness_status" = disabled ]; then status=disabled; fi
if [ "$has_infra_warnings" = true ] || [ "$has_missing_checks" = true ]; then status=incomplete; fi
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
  jq -n --arg message "$message" '{decision: "block", reason: $message, systemMessage: $message}'
  exit 0
fi

if [ "$has_missing_checks" = true ]; then
  message=$(printf '%b' "$output")
  jq -n --arg message "Verification is incomplete. ${message}" '{decision: "block", reason: $message, systemMessage: $message}'
  exit 0
fi

exit 0
