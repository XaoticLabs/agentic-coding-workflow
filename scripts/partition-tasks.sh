#!/usr/bin/env bash
# Canonical partition entry point; parsing and graph validation are shared.
set -euo pipefail
exec python3 "$(dirname "$(realpath "$0")")/task-plan.py" partition "$@"
