#!/bin/bash
# Shared infrastructure failure patterns — used by lint subscripts
# Tight list: only patterns that are NEVER caused by code bugs

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
