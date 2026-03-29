#!/usr/bin/env bash
# Analyze a parallel Ralph run from the unified trace and worker artifacts.
#
# Produces a markdown report with:
#   - Worker comparison table (iterations, kept, reverted, duration, files)
#   - File overlap violations (same file touched by 2+ workers)
#   - Merge conflict report
#   - Wave execution timeline
#   - Idle time analysis
#
# Usage: analyze-parallel-run.sh <artifact-base-dir> [merge-result-json]
# Output: parallel-analysis.md in the artifact base directory

set -euo pipefail

ARTIFACT_BASE="${1:?Usage: analyze-parallel-run.sh <artifact-base-dir> [merge-result-json]}"
MERGE_RESULT="${2:-}"

OUTPUT="${ARTIFACT_BASE}/parallel-analysis.md"
UNIFIED_TRACE="${ARTIFACT_BASE}/unified-trace.jsonl"

python3 - "$ARTIFACT_BASE" "$MERGE_RESULT" "$UNIFIED_TRACE" "$OUTPUT" <<'PYEOF'
import sys, json, os
from collections import defaultdict
from datetime import datetime

artifact_base = sys.argv[1]
merge_result_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
unified_trace_path = sys.argv[3]
output_path = sys.argv[4]

# ── Load unified trace ─────────────────────────────────────────────
events = []
if os.path.exists(unified_trace_path):
    with open(unified_trace_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except:
                pass

# ── Load merge result ──────────────────────────────────────────────
merge_result = {}
if merge_result_path and os.path.exists(merge_result_path):
    try:
        with open(merge_result_path) as f:
            merge_result = json.load(f)
    except:
        pass

# ── Analyze per-worker metrics ─────────────────────────────────────
workers = defaultdict(lambda: {
    "iterations": 0, "kept": 0, "reverted": 0, "timeouts": 0,
    "files_changed": set(), "first_event": None, "last_event": None,
    "duration_m": 0
})

for e in events:
    source = e.get("source", "")
    if source == "orchestrator" or not source:
        continue
    # Accept both "worker-0" and "wave0-worker-0" formats
    if "worker" not in source:
        continue

    ts = e.get("ts", "")
    w = workers[source]

    if w["first_event"] is None or ts < w["first_event"]:
        w["first_event"] = ts
    if w["last_event"] is None or ts > w["last_event"]:
        w["last_event"] = ts

    etype = e.get("type", "")

    if etype == "iteration_end":
        w["iterations"] += 1

    if etype == "verdict":
        outcome = e.get("outcome", "")
        if outcome == "KEEP":
            w["kept"] += 1
            # Track files changed
            files = e.get("files_changed", "")
            if files:
                for f in files.split(","):
                    f = f.strip()
                    if f:
                        w["files_changed"].add(f)
        elif outcome.startswith("REVERT"):
            w["reverted"] += 1
        elif outcome == "TIMEOUT":
            w["timeouts"] += 1

    if etype == "run_end":
        w["duration_m"] = e.get("duration_m", 0)

# ── File overlap analysis ──────────────────────────────────────────
file_to_workers = defaultdict(set)
for wid, w in workers.items():
    for f in w["files_changed"]:
        file_to_workers[f].add(wid)

overlapping_files = {f: ws for f, ws in file_to_workers.items() if len(ws) > 1}

# ── Build report ───────────────────────────────────────────────────
lines = []
lines.append("# Parallel Run Analysis\n")
lines.append(f"**Generated:** {datetime.utcnow().isoformat()}Z\n")

# Worker comparison table
lines.append("## Worker Comparison\n")
lines.append("| Worker | Iterations | Kept | Reverted | Timeouts | Files | Duration |")
lines.append("|--------|-----------|------|----------|----------|-------|----------|")

for wid in sorted(workers.keys()):
    w = workers[wid]
    success_rate = f"{w['kept']*100//max(w['iterations'],1)}%" if w["iterations"] > 0 else "N/A"
    lines.append(
        f"| {wid} | {w['iterations']} | {w['kept']} ({success_rate}) | "
        f"{w['reverted']} | {w['timeouts']} | {len(w['files_changed'])} | "
        f"{w['duration_m']}m |"
    )

# File overlap violations
lines.append("\n## File Overlap Violations\n")
if overlapping_files:
    lines.append(f"**{len(overlapping_files)} files** touched by multiple workers (partition leak):\n")
    for f, ws in sorted(overlapping_files.items()):
        lines.append(f"- `{f}` — {', '.join(sorted(ws))}")
else:
    lines.append("No file overlap violations detected. Partition was clean.\n")

# Merge results
lines.append("\n## Merge Results\n")
if merge_result:
    lines.append(f"- **Status:** {merge_result.get('status', 'unknown')}")
    lines.append(f"- **Merged:** {merge_result.get('merged', 0)}")
    lines.append(f"- **Skipped:** {merge_result.get('skipped', 0)}")
    lines.append(f"- **Failed:** {merge_result.get('failed', 0)}")
    lines.append(f"- **Conflicts resolved:** {merge_result.get('conflicts_resolved', 0)}")

    results = merge_result.get("results", [])
    if results:
        lines.append("\n| Branch | Status | Details |")
        lines.append("|--------|--------|---------|")
        for r in results:
            details = r.get("reason", r.get("commits", ""))
            lines.append(f"| `{r.get('branch','')}` | {r.get('status','')} | {details} |")
else:
    lines.append("No merge result data available.\n")

# Workload balance
lines.append("\n## Workload Balance\n")
if workers:
    iter_counts = [w["iterations"] for w in workers.values()]
    if iter_counts and max(iter_counts) > 0:
        balance_ratio = min(iter_counts) / max(iter_counts)
        lines.append(f"- **Balance ratio:** {balance_ratio:.2f} (1.0 = perfectly balanced)")
        lines.append(f"- **Min iterations:** {min(iter_counts)}")
        lines.append(f"- **Max iterations:** {max(iter_counts)}")
        if balance_ratio < 0.5:
            lines.append("- **Warning:** Significant workload imbalance detected. Consider rebalancing task assignment.")

# Timeline
lines.append("\n## Timeline\n")
lines.append("```")
for wid in sorted(workers.keys()):
    w = workers[wid]
    start = w["first_event"] or "?"
    end = w["last_event"] or "?"
    bar_len = max(1, w["kept"])
    bar = "#" * bar_len + "x" * w["reverted"]
    lines.append(f"{wid}: [{start[:19]}] {'=' * min(40, w['iterations'])}> [{end[:19]}]  {bar}")
lines.append("```")
lines.append(f"\n`#` = kept iteration, `x` = reverted iteration\n")

# Write report
with open(output_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Analysis written to: {output_path}")
PYEOF
