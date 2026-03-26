#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Ralph Trace Viewer — reads JSONL trace files and renders human-readable views.

Usage: trace-viewer.py <trace-file> [--view timeline|summary|tools|reverts]
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime


# ANSI colors
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def load_events(path: str) -> list[dict]:
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def short_ts(ts: str) -> str:
    """Extract HH:MM:SS from ISO timestamp."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except Exception:
        return ts[:8] if len(ts) >= 8 else ts


def view_timeline(events: list[dict]):
    """Chronological event display with colors."""
    for ev in events:
        ts = short_ts(ev.get("ts", ""))
        etype = ev.get("type", "")

        if etype == "run_start":
            slug = ev.get("slug", "?")
            mode = ev.get("mode", "?")
            max_iters = ev.get("max_iters", "?")
            print(f"\n{BOLD}{ts}  RUN_START{RESET}  slug={slug} mode={mode} max_iters={max_iters}")

        elif etype == "plan_state":
            done = ev.get("done", 0)
            total = ev.get("total", 0)
            remaining = ev.get("remaining", 0)
            print(f"  {DIM}{ts}  PLAN   {done}/{total} done, {remaining} remaining{RESET}")

        elif etype == "prompt_built":
            prompt_bytes = ev.get("prompt_bytes", 0)
            kb = prompt_bytes // 1024
            print(f"  {DIM}{ts}  PROMPT {kb}KB{RESET}")

        elif etype == "struggle_warning":
            task = ev.get("task", "?")
            retry = ev.get("retry", "?")
            threshold = ev.get("threshold", "?")
            print(f"  {YELLOW}{ts}  STRUGGLE  retry {retry}/{threshold} on: {task}{RESET}")

        elif etype == "iteration_start":
            it = ev.get("iter", "?")
            task = ev.get("task", "")
            print(f"\n{BOLD}{ts}  ITER {it}{RESET}  {DIM}task={task}{RESET}")

        elif etype == "tool_call":
            tool = ev.get("tool", "?")
            summary = ev.get("input_summary", "")
            dur = ev.get("duration_ms", 0)
            dur_str = f"  {DIM}({dur}ms){RESET}" if dur > 500 else ""
            print(f"  {BLUE}{ts}{RESET}  {tool:<6} {summary[:90]}{dur_str}")

        elif etype == "gate":
            gate = ev.get("gate", "?")
            passed = ev.get("passed", False)
            color = GREEN if passed else RED
            status = "PASS" if passed else "FAIL"
            extra = ""
            if not passed:
                tail = ev.get("output_tail", "")
                if tail:
                    extra = f"  {DIM}{tail[:80]}{RESET}"
            print(f"  {color}{ts}  GATE  {gate}: {status}{RESET}{extra}")

        elif etype == "verdict":
            outcome = ev.get("outcome", "?")
            task = ev.get("task", "")
            if "KEEP" in outcome:
                color = GREEN
            elif "TIMEOUT" in outcome:
                color = YELLOW
            else:
                color = RED
            extra = ""
            commit_msg = ev.get("commit_msg", "")
            diff_stat = ev.get("diff_stat", "")
            if commit_msg:
                extra = f"\n           {DIM}msg: {commit_msg[:80]}{RESET}"
            if diff_stat:
                extra += f"\n           {DIM}{diff_stat}{RESET}"
            print(f"  {color}{BOLD}{ts}  VERDICT  {outcome}{RESET}  {DIM}{task}{RESET}{extra}")

        elif etype == "iteration_end":
            dur = ev.get("duration_s", 0)
            commit = ev.get("commit", "")[:8]
            outcome = ev.get("outcome", "")
            if "success" in outcome or outcome == "KEEP":
                color = GREEN
            elif "timeout" in outcome:
                color = YELLOW
            elif "revert" in outcome:
                color = RED
            else:
                color = DIM
            print(f"  {color}{ts}  ITER_END  {outcome}  {dur}s  {commit}{RESET}")

        elif etype == "injection":
            content = ev.get("content", "")[:80]
            print(f"  {CYAN}{ts}  INJECTION  {content}{RESET}")

        elif etype == "circuit_break":
            cb_type = ev.get("cb_type", ev.get("type_detail", ""))
            reason = ev.get("reason", "")
            print(f"  {RED}{BOLD}{ts}  CIRCUIT_BREAK ({cb_type})  {reason}{RESET}")

        elif etype == "run_end":
            iters = ev.get("total_iters", "?")
            kept = ev.get("kept", "?")
            reverted = ev.get("reverted", "?")
            dur = ev.get("duration_m", "?")
            print(f"\n{BOLD}{ts}  RUN_END{RESET}  {iters} iters, {GREEN}{kept} kept{RESET}, {RED}{reverted} reverted{RESET}, {dur} min")

        elif etype == "message_end":
            tool_calls = ev.get("tool_calls", 0)
            in_tok = ev.get("input_tokens", 0)
            out_tok = ev.get("output_tokens", 0)
            summary = ev.get("iteration_summary", "")
            tok_str = ""
            if in_tok or out_tok:
                tok_str = f"  {DIM}({in_tok + out_tok} tokens: {in_tok} in, {out_tok} out){RESET}"
            if summary:
                print(f"  {DIM}{ts}  SUMMARY  {summary[:120]}{RESET}")
            print(f"  {DIM}{ts}  ── {tool_calls} tool calls{tok_str} ──{RESET}")

        elif etype == "api_retry":
            attempt = ev.get("attempt", "?")
            status = ev.get("error_status", "?")
            print(f"  {YELLOW}{ts}  API_RETRY  attempt={attempt} status={status}{RESET}")


def view_summary(events: list[dict]):
    """Compact run overview with metrics."""
    run_start = None
    run_end = None
    verdicts = []
    iterations = []
    message_ends = []
    prompt_events = []

    for ev in events:
        etype = ev.get("type", "")
        if etype == "run_start":
            run_start = ev
        elif etype == "run_end":
            run_end = ev
        elif etype == "verdict":
            verdicts.append(ev)
        elif etype == "iteration_end":
            iterations.append(ev)
        elif etype == "message_end":
            message_ends.append(ev)
        elif etype == "prompt_built":
            prompt_events.append(ev)

    if run_start:
        print(f"{BOLD}Ralph Run Summary{RESET}")
        print(f"  Slug:       {run_start.get('slug', '?')}")
        print(f"  Mode:       {run_start.get('mode', '?')}")
        print(f"  Max iters:  {run_start.get('max_iters', '?')}")
        print()

    outcomes = Counter(v.get("outcome", "?") for v in verdicts)
    total = len(verdicts)
    kept = sum(1 for v in verdicts if "KEEP" in v.get("outcome", ""))
    reverted = sum(1 for v in verdicts if "REVERT" in v.get("outcome", ""))
    timeouts = sum(1 for v in verdicts if "TIMEOUT" in v.get("outcome", ""))
    no_commits = sum(1 for v in verdicts if "NO_COMMIT" in v.get("outcome", ""))

    real = kept + reverted + timeouts
    rate = f"{kept * 100 // real}%" if real > 0 else "N/A"

    print(f"  {BOLD}Iterations:{RESET}   {len(iterations)}")
    print(f"  {GREEN}Kept:{RESET}         {kept}")
    print(f"  {RED}Reverted:{RESET}     {reverted}")
    print(f"  {YELLOW}Timeouts:{RESET}    {timeouts}")
    print(f"  {DIM}No-ops:{RESET}      {no_commits}")
    print(f"  {BOLD}Success rate:{RESET} {rate}")

    if run_end:
        print(f"  {BOLD}Duration:{RESET}     {run_end.get('duration_m', '?')} minutes")

    # Durations
    if iterations:
        durations = [i.get("duration_s", 0) for i in iterations if i.get("duration_s")]
        if durations:
            avg = sum(durations) // len(durations)
            print(f"  {DIM}Avg iter:{RESET}     {avg}s")
            print(f"  {DIM}Min/Max:{RESET}      {min(durations)}s / {max(durations)}s")

    # Token usage
    if message_ends:
        total_in = sum(m.get("input_tokens", 0) for m in message_ends)
        total_out = sum(m.get("output_tokens", 0) for m in message_ends)
        total_tok = total_in + total_out
        if total_tok > 0:
            print()
            print(f"  {BOLD}Token usage:{RESET}")
            print(f"    Input:    {total_in:,}")
            print(f"    Output:   {total_out:,}")
            print(f"    Total:    {total_tok:,}")
            if len(message_ends) > 0:
                avg_tok = total_tok // len(message_ends)
                print(f"    Avg/iter: {avg_tok:,}")

    # Prompt sizes
    if prompt_events:
        sizes = [p.get("prompt_bytes", 0) for p in prompt_events]
        if sizes:
            avg_kb = (sum(sizes) // len(sizes)) // 1024
            max_kb = max(sizes) // 1024
            min_kb = min(sizes) // 1024
            print()
            print(f"  {BOLD}Prompt size:{RESET}")
            print(f"    Avg: {avg_kb}KB  Min: {min_kb}KB  Max: {max_kb}KB")
            if max_kb > avg_kb * 2 and avg_kb > 0:
                print(f"    {YELLOW}Warning: prompt size grew significantly — may indicate bloat{RESET}")

    print()
    print(f"  {BOLD}Outcome breakdown:{RESET}")
    for outcome, count in outcomes.most_common():
        print(f"    {outcome}: {count}")


def view_tools(events: list[dict]):
    """Tool usage breakdown."""
    tool_counts: Counter = Counter()
    tool_durations: defaultdict[str, list[int]] = defaultdict(list)
    read_files: Counter = Counter()
    bash_commands: Counter = Counter()

    for ev in events:
        if ev.get("type") != "tool_call":
            continue
        tool = ev.get("tool", "?")
        tool_counts[tool] += 1
        dur = ev.get("duration_ms", 0)
        if dur:
            tool_durations[tool].append(dur)
        summary = ev.get("input_summary", "")
        if tool == "Read" and summary:
            read_files[summary] += 1
        elif tool == "Bash" and summary:
            # Normalize common commands
            cmd = summary.split()[0] if summary.split() else summary
            bash_commands[cmd] += 1

    total = sum(tool_counts.values())
    print(f"{BOLD}Tool Usage ({total} total calls){RESET}\n")

    print(f"  {'Tool':<12} {'Count':>6}  {'Avg ms':>8}  {'Total ms':>10}")
    print(f"  {'─' * 12} {'─' * 6}  {'─' * 8}  {'─' * 10}")
    for tool, count in tool_counts.most_common():
        durs = tool_durations.get(tool, [])
        avg_ms = sum(durs) // len(durs) if durs else 0
        total_ms = sum(durs)
        print(f"  {tool:<12} {count:>6}  {avg_ms:>8}  {total_ms:>10}")

    if read_files:
        print(f"\n{BOLD}Most-Read Files{RESET}")
        for path, count in read_files.most_common(10):
            print(f"  {count:>3}x  {path}")

    if bash_commands:
        print(f"\n{BOLD}Bash Command Prefixes{RESET}")
        for cmd, count in bash_commands.most_common(10):
            print(f"  {count:>3}x  {cmd}")


def view_reverts(events: list[dict]):
    """Focus on failed iterations."""
    current_iter = None
    current_task = ""
    gates_failed = []
    revert_count = 0

    task_reverts: Counter = Counter()

    for ev in events:
        etype = ev.get("type", "")

        if etype == "iteration_start":
            current_iter = ev.get("iter")
            current_task = ev.get("task", "")
            gates_failed = []

        elif etype == "gate" and not ev.get("passed", True):
            gates_failed.append(ev)

        elif etype == "verdict" and "REVERT" in ev.get("outcome", ""):
            revert_count += 1
            outcome = ev.get("outcome", "")
            task = ev.get("task", current_task)
            task_reverts[task] += 1

            print(f"{RED}{BOLD}Iteration {current_iter}: {outcome}{RESET}")
            print(f"  Task: {task}")
            for gate in gates_failed:
                gate_name = gate.get("gate", "?")
                tail = gate.get("output_tail", "")
                print(f"  Gate: {RED}{gate_name} FAILED{RESET}")
                if tail:
                    for line in tail.split("\n")[:5]:
                        print(f"    {DIM}{line}{RESET}")
            print()

        elif etype == "verdict" and "TIMEOUT" in ev.get("outcome", ""):
            revert_count += 1
            task = ev.get("task", current_task)
            task_reverts[task] += 1
            print(f"{YELLOW}{BOLD}Iteration {current_iter}: TIMEOUT{RESET}")
            print(f"  Task: {task}")
            print()

    if revert_count == 0:
        print(f"{GREEN}No reverts in this run!{RESET}")
        return

    print(f"\n{BOLD}Revert Summary ({revert_count} total){RESET}")
    for task, count in task_reverts.most_common():
        print(f"  {count:>3}x  {task}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Ralph trace viewer")
    parser.add_argument("trace_file", help="Path to JSONL trace file")
    parser.add_argument("--view", choices=["timeline", "summary", "tools", "reverts"],
                        default="timeline", help="View to render (default: timeline)")
    args = parser.parse_args()

    events = load_events(args.trace_file)
    if not events:
        print("No events found in trace file.", file=sys.stderr)
        sys.exit(1)

    views = {
        "timeline": view_timeline,
        "summary": view_summary,
        "tools": view_tools,
        "reverts": view_reverts,
    }
    views[args.view](events)


if __name__ == "__main__":
    main()
