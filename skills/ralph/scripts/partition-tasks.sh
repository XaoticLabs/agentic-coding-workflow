#!/usr/bin/env bash
# Thin wrapper — canonical script lives in scripts/partition-tasks.sh
# Kept here so orchestrate-parallel.sh's $SCRIPT_DIR reference still works
PLUGIN_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
exec "$PLUGIN_ROOT/scripts/partition-tasks.sh" "$@"
