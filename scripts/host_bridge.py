#!/usr/bin/env python3
"""Translate native host calls to existing prompts and registered hook scripts.

The runtime bridge uses only Python's standard library. Claude definitions and
hook registration remain authoritative; adapters translate transports, not policy.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys

from workflow_execution import terminate

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("pi", "autolith")
KINDS = {"command": "commands", "skill": "skills", "agent": "agents"}


def shell_roots(command: str) -> str:
    """Quote unquoted package variables without breaking authored shell quotes."""
    output, quote, offset = [], None, 0
    while offset < len(command):
        character = command[offset]
        if character == "\\" and quote != "'" and offset + 1 < len(command):
            output.append(command[offset : offset + 2])
            offset += 2
            continue
        if character in ("'", '"'):
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
        variable = next(
            (
                value
                for value in ("${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PROJECT_DIR}")
                if command.startswith(value, offset)
            ),
            None,
        )
        if variable and quote is None:
            output.append('"' + variable + '"')
            offset += len(variable)
        else:
            output.append(character)
            offset += 1
    return "".join(output)


def captured(
    command: list[str], *, cwd: Path, env: dict, timeout: float, input: str = ""
) -> subprocess.CompletedProcess:
    """Bound hooks and dynamic context, cleaning up their owned descendants."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input, timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        terminate(process)


def catalog(root: Path = ROOT) -> dict:
    data = json.loads((root / "hosts/catalog.json").read_text())
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Invalid host catalog; run maak sync-hosts")
    return data


def expand_text(
    text: str, host: str, project: Path, source: str = "", root: Path = ROOT
) -> str:
    if host not in HOSTS:
        raise ValueError(f"Unknown host: {host}")
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", str(root))
    text = text.replace("${CLAUDE_PROJECT_DIR}", str(project))
    text = text.replace("${CLAUDE_SKILL_DIR}", str(root / source).rsplit("/", 1)[0])
    text = re.sub(
        r"/agentic-coding-workflow:([a-z][a-z0-9-]*)",
        lambda m: f"/{m[1]}" if host == "pi" else f"/workflow-{m[1]}",
        text,
    )
    text = text.replace("command -v claude", f"command -v {host}")
    session_runner = f"bash {shlex.quote(str(root / 'scripts/spawn-session.sh'))}"
    text = re.sub(
        r"\bclaude --plugin-dir (?:\"[^\"]*\"|'[^']*'|[^\s`]+) --agent agentic-coding-workflow:([a-z][a-z0-9-]*)",
        lambda m: f"{session_runner} {m[1]} --host {host}",
        text,
    )
    text = re.sub(
        r"\bclaude --worktree ([^\s`]+) --tmux\b",
        lambda m: f"{session_runner} implementer --host {host} --worktree {m[1]}",
        text,
    )
    text = re.sub(
        r"\bclaude --resume ([^\s`]+)",
        lambda m: f"{session_runner} --host {host} --resume {m[1]}",
        text,
    )
    tools = (
        {
            "Bash": "bash",
            "Read": "read",
            "Write": "write",
            "Edit": "edit",
            "MultiEdit": "edit",
            "Grep": "grep",
            "Glob": "find",
            "Agent": "task",
        }
        if host == "pi"
        else {
            "Bash": "shell.run",
            "Read": "resource.read",
            "Write": "resource.edit",
            "Edit": "resource.edit",
            "MultiEdit": "resource.edit",
            "Grep": "search.content",
            "Glob": "search.glob",
            "Agent": "task.run",
            "WebSearch": "web.run",
            "WebFetch": "web.run",
            "TodoWrite": "plan.update",
        }
    )
    # Translate tool identifiers, not ordinary words in prose or shell commands.
    for old, new in tools.items():
        text = text.replace(f"`{old}`", f"`{new}`")
        text = re.sub(rf"\b{old}(?=\s+tool\b|\()", new, text)
    runner = f"python3 {shlex.quote(str(root / 'scripts/host-runner.py'))} prompt --host {host}"
    text = re.sub(r"(?<![\w/.-])claude(?=\s+(?:--|-p\b))", lambda _: runner, text)
    if host == "autolith":
        for old, instruction in {
            "AskUserQuestion": "ask the user in your response and wait for their reply",
            "EnterPlanMode": "begin planning using inspection tools only",
            "ExitPlanMode": "present the plan and wait for user approval",
        }.items():
            text = text.replace(old, instruction)
    return text


def render(
    host: str, kind: str, name: str, arguments: str, project: Path, root: Path = ROOT
) -> dict:
    if kind not in KINDS:
        raise ValueError(f"Unknown definition kind: {kind}")
    entry = catalog(root).get(KINDS[kind], {}).get(name)
    if not isinstance(entry, dict):
        raise ValueError(f"Unknown {kind}: {name}")
    body = entry["body"]

    # Execute only package-authored dynamic snippets, before inserting arguments.
    # User arguments can never introduce new prompt-preprocessing commands.
    def inject(match: re.Match) -> str:
        command = shell_roots(match[1])
        result = captured(
            ["bash", "-o", "pipefail", "-c", command],
            cwd=project,
            env={
                **os.environ,
                "CLAUDE_PLUGIN_ROOT": str(root),
                "CLAUDE_PROJECT_DIR": str(project),
                "WORKFLOW_HOST": host,
            },
            timeout=30,
        )
        if result.returncode:
            raise ValueError(
                f"Dynamic context command failed ({result.returncode}): {result.stderr[-2000:]}"
            )
        return result.stdout.rstrip()

    body = re.sub(r"!`([^`\n]+)`", inject, body)
    body = expand_text(body, host, project, entry["source"], root)
    body = body.replace("$ARGUMENTS", arguments)
    prefix = f"Workflow host: {host}. Plugin root: {root}. Project directory: {project}.\nSource: {entry['source']}. Resolve bundled relative resources against {(root / entry['source']).parent}.\n\n"
    return {**entry, "prompt": prefix + body}


def hook_event(event: str, data: dict, root: Path = ROOT) -> dict:
    response = {"action": "allow", "reason": "", "context": [], "outputs": []}
    if not isinstance(data, dict):
        raise ValueError("Hook input must be an object")
    project = Path(
        data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()
    ).resolve(strict=True)
    if not project.is_dir():
        raise ValueError("Hook project directory is unavailable")
    payload = {**data, "cwd": str(project), "hook_event_name": event}
    registrations = json.loads((root / "hooks/hooks.json").read_text())["hooks"]
    if event not in registrations:
        raise ValueError(f"Unknown hook event: {event}")
    for group in registrations[event]:
        matcher = group.get("matcher")
        matched_value = (
            payload.get("notification_type", "")
            if event == "Notification"
            else payload.get("tool_name", "")
        )
        if matcher and not re.fullmatch(matcher, matched_value):
            continue
        for hook in group["hooks"]:
            if hook.get("type") != "command":
                raise ValueError(f"Unsupported registered hook type for {event}")
            command = ["bash", "-o", "pipefail", "-c", shell_roots(hook["command"])]
            policy = event in {"PreToolUse", "Stop"}
            try:
                result = captured(
                    command,
                    input=json.dumps(payload),
                    cwd=project,
                    env={
                        **os.environ,
                        "CLAUDE_PLUGIN_ROOT": str(root),
                        "CLAUDE_PROJECT_DIR": str(project),
                    },
                    timeout=hook.get("timeout", 30),
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                if policy:
                    response.update(
                        action="halt",
                        reason=f"{event} policy hook unavailable: {error}",
                    )
                    return response
                response["outputs"].append({"error": str(error)})
                continue
            raw = result.stdout.strip()
            try:
                output = json.loads(raw) if raw else {}
                if not isinstance(output, dict):
                    raise ValueError("Hook output must be an object")
            except (ValueError, TypeError) as error:
                if policy:
                    response.update(
                        action="halt", reason=f"Invalid {event} policy output: {error}"
                    )
                    return response
                output = {}
            response["outputs"].append(
                {
                    "exit_code": result.returncode,
                    "output": output,
                    "stderr": result.stderr[-4000:],
                }
            )
            detail = output.get("hookSpecificOutput", {})
            context = (
                detail.get("additionalContext") if isinstance(detail, dict) else None
            )
            if context:
                response["context"].append(str(context))
            if output.get("systemMessage"):
                response["context"].append(str(output["systemMessage"]))
            if policy and (result.returncode not in (0, 2)):
                response.update(
                    action="halt",
                    reason=f"{event} policy hook exited {result.returncode}: {result.stderr[-2000:]}",
                )
                return response
            if output.get("continue") is False:
                response.update(
                    action="halt",
                    reason=str(
                        output.get("stopReason")
                        or output.get("systemMessage")
                        or "Workflow verification remains blocked"
                    ),
                )
                return response
            denied = (
                isinstance(detail, dict) and detail.get("permissionDecision") == "deny"
            )
            if result.returncode == 2 or output.get("decision") == "block" or denied:
                reason = str(
                    output.get("reason")
                    or detail.get("permissionDecisionReason")
                    or result.stderr
                    or "Workflow policy blocked this action"
                )
                response.update(action="repair", reason=reason)
                # Stop hooks are an ordered gate: do not run checks or notices
                # after an earlier gate blocks, even though native Claude may
                # dispatch registered commands concurrently.
                return response
    return response


def main() -> int:
    def interrupted(_signum, _frame):
        # Raising unwinds the capture's finally block and terminates its group.
        raise InterruptedError("Workflow bridge was cancelled")

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    renderer = sub.add_parser("render")
    renderer.add_argument("--kind", choices=KINDS, required=True)
    renderer.add_argument("--name", required=True)
    renderer.add_argument("--arguments", default="")
    text = sub.add_parser("render-text")
    text.add_argument("--source", default="")
    for target in (renderer, text):
        target.add_argument("--host", choices=HOSTS, required=True)
        target.add_argument("--project", type=Path, required=True)
    event = sub.add_parser("event")
    event.add_argument("--event", required=True)
    args = parser.parse_args()
    try:
        if args.operation == "event":
            output = hook_event(args.event, json.load(sys.stdin))
        else:
            project = args.project.resolve(strict=True)
            if not project.is_dir():
                raise ValueError("Project directory is unavailable")
            output = (
                render(args.host, args.kind, args.name, args.arguments, project)
                if args.operation == "render"
                else {
                    "text": expand_text(
                        sys.stdin.read(), args.host, project, args.source
                    )
                }
            )
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(
            json.dumps(
                {"action": "halt", "reason": str(error), "context": [], "outputs": []}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
