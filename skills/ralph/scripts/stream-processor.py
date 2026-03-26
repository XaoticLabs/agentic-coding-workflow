#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Ralph Stream Processor — sits between Claude's stream-json output and the terminal.

stdin:  stream-json from `claude -p --output-format stream-json`
stdout: reconstructed text output (captured to iter log file by loop.sh)
stderr: live activity display (visible in tmux pane)
trace:  JSONL events appended to --trace-file

Usage: stream-processor.py --trace-file <path> [--quiet]
"""

import json
import sys
import os
import time
from datetime import datetime, timezone


def ts_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_trace(trace_fd, event_type: str, **fields):
    """Append a JSONL event to the trace file."""
    event = {"ts": ts_now(), "type": event_type}
    event.update(fields)
    try:
        trace_fd.write(json.dumps(event, ensure_ascii=False) + "\n")
        trace_fd.flush()
    except Exception:
        pass


def summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    """Extract a compact human-readable summary from tool input."""
    if tool_name in ("Read", "Write"):
        return tool_input.get("file_path", "")[:120]
    if tool_name == "Edit":
        fp = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")
        # Show file path + rough location hint
        lines = old.count("\n") + 1
        return f"{fp} ({lines} lines)" if fp else ""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Truncate long commands
        return cmd[:120] + ("..." if len(cmd) > 120 else "")
    if tool_name in ("Grep", "Glob"):
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        return f"{pattern}" + (f" in {path}" if path else "")
    if tool_name == "Agent":
        desc = tool_input.get("description", "")
        return desc[:100]
    # Generic: show first string value
    for v in tool_input.values():
        if isinstance(v, str) and v:
            return v[:100]
    return ""


def display(msg: str, quiet: bool):
    """Write a line to stderr for the live tmux display."""
    if quiet:
        return
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Ralph stream processor")
    parser.add_argument("--trace-file", required=True, help="Path to JSONL trace file")
    parser.add_argument("--quiet", action="store_true", help="Suppress live display")
    args = parser.parse_args()

    # Open trace file in append mode
    os.makedirs(os.path.dirname(args.trace_file) or ".", exist_ok=True)
    trace_fd = open(args.trace_file, "a", encoding="utf-8")

    # Track content blocks by index
    blocks: dict[int, dict] = {}
    tool_count = 0
    last_text_block = ""  # Track the last/longest text block as iteration summary
    input_tokens = 0
    output_tokens = 0

    try:
        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            # Handle system events (retries, etc.)
            if data.get("type") == "system":
                subtype = data.get("subtype", "")
                if subtype == "api_retry":
                    display(
                        f"  {datetime.now().strftime('%H:%M:%S')}  ⟳ API retry "
                        f"(attempt {data.get('attempt', '?')}, "
                        f"status {data.get('error_status', '?')})",
                        args.quiet,
                    )
                    write_trace(trace_fd, "api_retry",
                                attempt=data.get("attempt", 0),
                                error_status=data.get("error_status", 0))
                continue

            # ── CLI stream-json format ──
            # `claude -p --verbose --output-format stream-json` emits high-level
            # events: {"type":"assistant","message":{...}} with complete content
            # blocks, and {"type":"result",...} with usage. Handle these first.
            top_type = data.get("type", "")

            if top_type == "assistant":
                msg = data.get("message", {})
                for block in msg.get("content", []):
                    bt = block.get("type", "")
                    if bt == "tool_use":
                        tool_count += 1
                        tool_name = block.get("name", "?")
                        tool_input = block.get("input", {})
                        summary = summarize_tool_input(tool_name, tool_input)
                        display(
                            f"  {datetime.now().strftime('%H:%M:%S')}  "
                            f"{tool_name:<6} {summary}",
                            args.quiet,
                        )
                        write_trace(trace_fd, "tool_call",
                                    tool=tool_name,
                                    input_summary=summary[:200],
                                    duration_ms=0)
                    elif bt == "text":
                        text = block.get("text", "")
                        if text.strip():
                            sys.stdout.write(text)
                            sys.stdout.flush()
                            if len(text) > len(last_text_block):
                                last_text_block = text
                            summary = text.strip()[:150].replace("\n", " ")
                            write_trace(trace_fd, "text_block", summary=summary)
                # Extract usage from the message if present
                usage = msg.get("usage", {})
                if usage:
                    input_tokens = usage.get("input_tokens", input_tokens)
                    output_tokens = usage.get("output_tokens", output_tokens)
                continue

            if top_type == "result":
                usage = data.get("usage", {})
                if usage:
                    input_tokens = usage.get("input_tokens", input_tokens)
                    output_tokens = usage.get("output_tokens", output_tokens)
                result_text = data.get("result", "")
                iter_summary = ""
                src = last_text_block or result_text
                if src:
                    tail = src.strip()[-500:]
                    para_break = tail.rfind("\n\n")
                    if para_break > 0:
                        iter_summary = tail[para_break:].strip()[:300]
                    else:
                        iter_summary = tail[-300:].strip()
                    iter_summary = iter_summary.replace("\n", " ")
                write_trace(trace_fd, "message_end",
                            tool_calls=tool_count,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            iteration_summary=iter_summary)
                display(
                    f"  {datetime.now().strftime('%H:%M:%S')}  "
                    f"── done ({tool_count} tool calls, "
                    f"{input_tokens + output_tokens} tokens) ──",
                    args.quiet,
                )
                continue

            # ── Low-level streaming API format (content_block_start/delta/stop) ──
            event = data.get("event", data)
            event_type = event.get("type", "")

            # ── content_block_start ──
            if event_type == "content_block_start":
                idx = event.get("index", 0)
                cb = event.get("content_block", {})
                block_type = cb.get("type", "")
                blocks[idx] = {
                    "type": block_type,
                    "name": cb.get("name", ""),
                    "id": cb.get("id", ""),
                    "input_chunks": [],
                    "text_chunks": [],
                    "start_time": time.time(),
                }
                if block_type == "tool_use":
                    tool_count += 1
                    display(
                        f"  {datetime.now().strftime('%H:%M:%S')}  "
                        f"{cb.get('name', '?'):<6} ...",
                        args.quiet,
                    )

            # ── content_block_delta ──
            elif event_type == "content_block_delta":
                idx = event.get("index", 0)
                delta = event.get("delta", {})
                delta_type = delta.get("type", "")
                block = blocks.get(idx)
                if not block:
                    continue

                if delta_type == "input_json_delta":
                    block["input_chunks"].append(delta.get("partial_json", ""))
                elif delta_type == "text_delta":
                    text = delta.get("text", "")
                    block["text_chunks"].append(text)
                    # Pass through text to stdout
                    sys.stdout.write(text)
                    sys.stdout.flush()
                elif delta_type == "thinking_delta":
                    # Show a brief thinking indicator
                    thinking = delta.get("thinking", "")
                    if thinking and len(thinking) > 20:
                        snippet = thinking[:80].replace("\n", " ")
                        display(
                            f"  {datetime.now().strftime('%H:%M:%S')}  "
                            f"{'think':<6} {snippet}...",
                            args.quiet,
                        )

            # ── content_block_stop ──
            elif event_type == "content_block_stop":
                idx = event.get("index", 0)
                block = blocks.pop(idx, None)
                if not block:
                    continue

                elapsed = time.time() - block["start_time"]

                if block["type"] == "tool_use":
                    # Parse accumulated input JSON
                    input_json_str = "".join(block["input_chunks"])
                    tool_input = {}
                    try:
                        if input_json_str:
                            tool_input = json.loads(input_json_str)
                    except json.JSONDecodeError:
                        tool_input = {"_raw": input_json_str[:500]}

                    tool_name = block["name"]
                    summary = summarize_tool_input(tool_name, tool_input)

                    # Update the live display line with the summary
                    display(
                        f"  {datetime.now().strftime('%H:%M:%S')}  "
                        f"{tool_name:<6} {summary}",
                        args.quiet,
                    )

                    write_trace(trace_fd, "tool_call",
                                tool=tool_name,
                                input_summary=summary[:200],
                                duration_ms=int(elapsed * 1000))

                elif block["type"] == "text":
                    full_text = "".join(block["text_chunks"])
                    if full_text.strip():
                        # Track the longest text block as the iteration summary
                        if len(full_text) > len(last_text_block):
                            last_text_block = full_text
                        # Emit a text block trace event with a short summary
                        summary = full_text.strip()[:150].replace("\n", " ")
                        write_trace(trace_fd, "text_block", summary=summary)

            # ── message_delta (carries usage data) ──
            elif event_type == "message_delta":
                usage = event.get("usage", {})
                if usage:
                    input_tokens = usage.get("input_tokens", input_tokens)
                    output_tokens = usage.get("output_tokens", output_tokens)

            # ── message_stop ──
            elif event_type == "message_stop":
                # Extract iteration summary from the last text block
                iter_summary = ""
                if last_text_block:
                    # Take last 500 chars — Claude typically summarizes at the end
                    tail = last_text_block.strip()[-500:]
                    # Find last paragraph break for a clean cut
                    para_break = tail.rfind("\n\n")
                    if para_break > 0:
                        iter_summary = tail[para_break:].strip()[:300]
                    else:
                        iter_summary = tail[-300:].strip()
                    iter_summary = iter_summary.replace("\n", " ")

                write_trace(trace_fd, "message_end",
                            tool_calls=tool_count,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            iteration_summary=iter_summary)
                display(
                    f"  {datetime.now().strftime('%H:%M:%S')}  "
                    f"── done ({tool_count} tool calls, "
                    f"{input_tokens + output_tokens} tokens) ──",
                    args.quiet,
                )

    except KeyboardInterrupt:
        pass
    except BrokenPipeError:
        pass
    finally:
        # Flush any remaining blocks as partial events
        for idx, block in blocks.items():
            if block["type"] == "tool_use":
                write_trace(trace_fd, "tool_call_partial",
                            tool=block["name"],
                            note="stream interrupted before completion")
        trace_fd.close()
        # Ensure stdout is flushed
        try:
            sys.stdout.flush()
        except Exception:
            pass


if __name__ == "__main__":
    main()
