#!/usr/bin/env bash
# Usage: stitch-traces.sh <worker-trace-dir> <slug> [orchestrator-trace] [output]
# Default output: <worker-trace-dir>/unified-trace.jsonl
set -euo pipefail
exec python3 "$(dirname "$(realpath "$0")")/stitch-traces.py" "$@"
