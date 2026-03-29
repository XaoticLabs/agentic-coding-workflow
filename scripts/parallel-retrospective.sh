#!/usr/bin/env bash
# Post-run retrospective: analyze parallelization strategy and accumulate learnings.
#
# Reads: unified trace, merge results
# Writes: learnings.json (persistent, accumulates across runs)
#         research-queue.md (autoresearch triggers)
#
# Usage: parallel-retrospective.sh <run-dir> <ralph-base> <slug>

set -euo pipefail

RUN_DIR="${1:?Usage: parallel-retrospective.sh <run-dir> <ralph-base> <slug>}"
RALPH_BASE="${2:?Usage: parallel-retrospective.sh <run-dir> <ralph-base> <slug>}"
SLUG="${3:?Usage: parallel-retrospective.sh <run-dir> <ralph-base> <slug>}"

LEARNINGS_FILE="${RALPH_BASE}/learnings.json"
RESEARCH_QUEUE="${RALPH_BASE}/research-queue.md"
UNIFIED_TRACE="${RUN_DIR}/trace.jsonl"

python3 - "$RUN_DIR" "$RALPH_BASE" "$SLUG" "$LEARNINGS_FILE" "$RESEARCH_QUEUE" "$UNIFIED_TRACE" <<'PYEOF'
import sys, json, os, glob
from collections import defaultdict
from datetime import datetime

run_dir = sys.argv[1]
ralph_base = sys.argv[2]
slug = sys.argv[3]
learnings_path = sys.argv[4]
research_path = sys.argv[5]
trace_path = sys.argv[6]

today = datetime.utcnow().strftime("%Y-%m-%d")

# ── Load existing learnings ────────────────────────────────────────
learnings = {"conflict_hotspots": {}, "task_duration_calibration": {}, "partition_violations": [], "run_history": []}
if os.path.exists(learnings_path):
    try:
        with open(learnings_path) as f:
            learnings = json.load(f)
    except:
        pass

# ── Load unified trace ─────────────────────────────────────────────
events = []
if os.path.exists(trace_path):
    with open(trace_path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                events.append(json.loads(line))
            except:
                pass

# ── Load merge results ─────────────────────────────────────────────
merge_results = []
# Try consolidated merge-results.json first, fall back to individual wave files
consolidated = os.path.join(run_dir, "merge-results.json")
if os.path.exists(consolidated):
    try:
        with open(consolidated) as f:
            data = json.load(f)
            merge_results = data if isinstance(data, list) else [data]
    except: pass
else:
    for mf in sorted(glob.glob(os.path.join(run_dir, "wave*-merge-result.json"))):
        try:
            with open(mf) as f:
                merge_results.append(json.load(f))
        except: pass

# ── Analyze: per-worker metrics ────────────────────────────────────
workers = defaultdict(lambda: {"iterations": 0, "kept": 0, "reverted": 0, "files": set(), "duration_m": 0})

for e in events:
    src = e.get("source", "")
    if not src.startswith("worker-") and not src.startswith("wave"):
        continue
    w = workers[src]
    etype = e.get("type", "")
    if etype == "iteration_end":
        w["iterations"] += 1
    if etype == "verdict":
        outcome = e.get("outcome", "")
        if outcome == "KEEP":
            w["kept"] += 1
            for f in e.get("files_changed", "").split(","):
                f = f.strip()
                if f: w["files"].add(f)
        elif outcome.startswith("REVERT"):
            w["reverted"] += 1
    if etype == "run_end":
        w["duration_m"] = e.get("duration_m", 0)

# ── Analyze: file overlap violations ───────────────────────────────
file_to_workers = defaultdict(set)
for wid, w in workers.items():
    for f in w["files"]:
        file_to_workers[f].add(wid)

violations = {f: sorted(ws) for f, ws in file_to_workers.items() if len(ws) > 1}

# Record violations
if violations:
    learnings["partition_violations"].append({
        "run": slug, "date": today,
        "files": list(violations.keys()),
        "details": {f: ws for f, ws in violations.items()}
    })
    # Keep only last 20 violation records
    learnings["partition_violations"] = learnings["partition_violations"][-20:]

# ── Analyze: merge conflicts ───────────────────────────────────────
conflict_files = set()
for mr in merge_results:
    for r in mr.get("results", []):
        if r.get("status") in ("merged_with_conflicts", "failed"):
            # Try to extract conflict files from test output or reason
            reason = r.get("reason", "")
            if "conflict" in reason.lower():
                conflict_files.add(r.get("branch", "unknown"))

# Update conflict hotspots from violations (files touched by multiple workers)
hotspots = learnings.get("conflict_hotspots", {})
for f in violations:
    if f in hotspots:
        hotspots[f]["conflicts"] = hotspots[f].get("conflicts", 0) + 1
        hotspots[f]["last_seen"] = today
    else:
        hotspots[f] = {"conflicts": 1, "last_seen": today}

# Prune stale hotspots (>90 days old)
cutoff = datetime.utcnow()
for f in list(hotspots.keys()):
    try:
        last = datetime.strptime(hotspots[f]["last_seen"], "%Y-%m-%d")
        if (cutoff - last).days > 90:
            del hotspots[f]
    except:
        pass
learnings["conflict_hotspots"] = hotspots

# ── Analyze: task duration calibration ─────────────────────────────
# Approximate: iterations per worker correlates with task complexity
calibration = learnings.get("task_duration_calibration", {})
for wid, w in workers.items():
    file_count = len(w["files"])
    if file_count > 0 and w["iterations"] > 0:
        bucket = str(file_count)
        if bucket in calibration:
            # Running average
            old = calibration[bucket]
            calibration[bucket] = round((old + w["iterations"]) / 2, 1)
        else:
            calibration[bucket] = w["iterations"]
learnings["task_duration_calibration"] = calibration

# ── Analyze: workload balance ──────────────────────────────────────
iter_counts = [w["iterations"] for w in workers.values() if w["iterations"] > 0]
balance_ratio = min(iter_counts) / max(iter_counts) if iter_counts and max(iter_counts) > 0 else 1.0

# ── Record run history ─────────────────────────────────────────────
total_merged = sum(mr.get("merged", 0) for mr in merge_results)
total_failed = sum(mr.get("failed", 0) for mr in merge_results)
total_conflicts = sum(mr.get("conflicts_resolved", 0) for mr in merge_results)

run_record = {
    "slug": slug, "date": today,
    "workers": len(workers), "violations": len(violations),
    "merged": total_merged, "failed": total_failed,
    "conflicts": total_conflicts, "balance_ratio": round(balance_ratio, 2)
}
history = learnings.get("run_history", [])
history.append(run_record)
learnings["run_history"] = history[-30:]  # Keep last 30 runs

# ── Save learnings ─────────────────────────────────────────────────
os.makedirs(os.path.dirname(learnings_path), exist_ok=True)
with open(learnings_path, "w") as f:
    json.dump(learnings, f, indent=2)
print(f"Learnings updated: {learnings_path}")
print(f"  Hotspots: {len(hotspots)}, Violations: {len(violations)}, Balance: {balance_ratio:.2f}")

# ── Autoresearch: detect weaknesses and generate research queue ────
research_items = []

# High conflict rate (>30% of runs in last 5 had conflicts)
recent = history[-5:]
conflict_runs = sum(1 for r in recent if r.get("conflicts", 0) > 0)
if len(recent) >= 3 and conflict_runs / len(recent) > 0.3:
    conflict_files_str = ", ".join(f"`{f}`" for f in sorted(hotspots.keys())[:5])
    research_items.append({
        "title": "Reduce merge conflict rate",
        "trigger": f"{conflict_runs}/{len(recent)} recent runs had conflicts",
        "context": f"Hotspot files: {conflict_files_str}",
        "question": "Should these files be split into per-module files that workers own exclusively?",
        "priority": "HIGH"
    })

# Persistent workload imbalance
imbalanced = sum(1 for r in recent if r.get("balance_ratio", 1) < 0.5)
if len(recent) >= 3 and imbalanced / len(recent) > 0.5:
    research_items.append({
        "title": "Fix workload imbalance across workers",
        "trigger": f"{imbalanced}/{len(recent)} recent runs had balance ratio < 0.5",
        "context": f"Task duration calibration: {json.dumps(calibration)}",
        "question": "Should partition-tasks.sh weight assignments by estimated duration instead of pure file affinity?",
        "priority": "MEDIUM"
    })

# Repeated violations on same files
repeat_violators = defaultdict(int)
for pv in learnings.get("partition_violations", [])[-10:]:
    for f in pv.get("files", []):
        repeat_violators[f] += 1
chronic = {f: c for f, c in repeat_violators.items() if c >= 3}
if chronic:
    files_str = ", ".join(f"`{f}`" for f in sorted(chronic.keys())[:5])
    research_items.append({
        "title": "Chronic partition violations",
        "trigger": f"{len(chronic)} files violated in 3+ runs",
        "context": f"Files: {files_str}",
        "question": "These files are repeatedly touched by multiple workers despite file-affinity. Consider adding them as mandatory single-worker files.",
        "priority": "HIGH"
    })

# Write research queue
if research_items:
    with open(research_path, "w") as f:
        f.write("# Parallel Workflow Research Queue\n\n")
        f.write(f"*Generated: {today} after run `{slug}`*\n\n")
        for item in research_items:
            f.write(f"## {item['title']}\n")
            f.write(f"**Trigger:** {item['trigger']}\n")
            f.write(f"**Context:** {item['context']}\n")
            f.write(f"**Question:** {item['question']}\n")
            f.write(f"**Priority:** {item['priority']}\n\n")
    print(f"Research queue: {len(research_items)} items → {research_path}")
else:
    print("No research triggers detected.")
PYEOF
