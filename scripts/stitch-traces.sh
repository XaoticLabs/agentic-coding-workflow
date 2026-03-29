#!/usr/bin/env bash
# Stitch worker traces + orchestrator trace into a unified parallel trace.
#
# Finds all worker trace files in subdirectories of the artifact base,
# prefixes events with worker source, interleaves by timestamp.
#
# Usage: stitch-traces.sh <artifact-base-dir> <slug> [orchestrator-trace]
# Output: unified-trace.jsonl in the artifact base directory

set -euo pipefail

ARTIFACT_BASE="${1:?Usage: stitch-traces.sh <artifact-base-dir> <slug> [orchestrator-trace]}"
SLUG="${2:?Usage: stitch-traces.sh <artifact-base-dir> <slug> [orchestrator-trace]}"
ORCHESTRATOR_TRACE="${3:-}"

OUTPUT="${ARTIFACT_BASE}/unified-trace.jsonl"

# Collect all trace files with worker prefix
TEMP_FILE=$(mktemp)
trap "rm -f '$TEMP_FILE'" EXIT

# Add orchestrator events (no worker prefix)
if [ -n "$ORCHESTRATOR_TRACE" ] && [ -f "$ORCHESTRATOR_TRACE" ]; then
  python3 -c "
import sys, json
with open('${ORCHESTRATOR_TRACE}') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            e = json.loads(line)
            e['source'] = 'orchestrator'
            print(json.dumps(e, separators=(',', ':')))
        except: pass
" >> "$TEMP_FILE"
fi

# Find all worker trace files by globbing subdirectories
# Handles both flat (worker-0/) and wave-based (wave0-worker-0/) naming
for trace_file in "${ARTIFACT_BASE}"/*/*-trace.jsonl; do
  [ -f "$trace_file" ] || continue

  # Derive worker source from parent directory name
  worker_dir=$(basename "$(dirname "$trace_file")")

  python3 -c "
import sys, json
worker_id = '${worker_dir}'
with open('${trace_file}') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            e = json.loads(line)
            e['source'] = worker_id
            print(json.dumps(e, separators=(',', ':')))
        except: pass
" >> "$TEMP_FILE"
done

# Sort by timestamp and write output
if [ -s "$TEMP_FILE" ]; then
  python3 -c "
import sys, json

events = []
with open('${TEMP_FILE}') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            e = json.loads(line)
            events.append(e)
        except: pass

# Sort by timestamp
events.sort(key=lambda e: e.get('ts', ''))

for e in events:
    print(json.dumps(e, separators=(',', ':')))
" > "$OUTPUT"

  EVENT_COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
  echo "Unified trace: ${OUTPUT} (${EVENT_COUNT} events)"
else
  echo "No trace events found to stitch."
fi
