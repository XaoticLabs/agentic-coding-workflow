#!/usr/bin/env python3
"""Run explicitly selected hosts behind the workflow's existing contracts."""

import argparse
import json
import os
from pathlib import Path
import signal
import shlex
import shutil
import re
import time
import subprocess
import sys
import uuid

from workflow_hosts import (
    HOSTS,
    ROOT,
    autolith_result,
    pi_result,
    pi_resume_path,
    require_host,
    schema_sexp,
    selected_host,
    sexp_string,
)
from workflow_models import VARIABLES, model_arguments
from workflow_execution import positive, terminate


def render_role(host: str, role: str, project: Path) -> str:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/host-bridge.py"),
            "render", "--host", host, "--kind", "agent", "--name", role,
            "--project", str(project),
        ],
        capture_output=True, text=True, check=True, timeout=30,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or not isinstance(value.get("prompt"), str):
        raise ValueError("Host renderer returned no role instructions")
    return value["prompt"]


def role_tools(role: str) -> list[str]:
    read = ["read", "grep", "find", "ls"]
    if role == "evaluator":
        return read
    if role == "runtime-verifier":
        return [*read, "bash"]
    if role not in ("implementer", "test-writer"):
        raise ValueError(f"Unknown workflow agent role: {role}")
    return [*read, "bash", "write", "edit"]


def expand_workflow_prompt(host: str, prompt: str, project: Path) -> str:
    """Headless invocations expand before native print-session disposal.

    Interactive command handlers queue follow-up messages. Print-mode callers
    instead need one complete prompt to keep the native inference alive.
    """
    match = re.fullmatch(r"\s*/(?:(skill:|agentic-coding-workflow:|workflow-))?([a-z0-9-]+)(?:[ \t]+([\s\S]*))?\s*", prompt)
    if not match:
        return prompt
    prefix, name, arguments = match.groups()
    catalog = json.loads((ROOT / "hosts/catalog.json").read_text())
    kinds = ("skill",) if prefix == "skill:" else ("command", "skill")
    for kind in kinds:
        entry = catalog[kind + "s"].get(name)
        if entry is None:
            continue
        if not entry.get("user_invocable"):
            raise ValueError(f"Workflow {name} is available to the model only")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/host-bridge.py"), "render", "--host", host,
             "--kind", kind, "--name", name, "--arguments", arguments or "", "--project", str(project)],
            text=True, capture_output=True, check=True, timeout=30,
        )
        rendered = json.loads(result.stdout)
        if not isinstance(rendered, dict) or not isinstance(rendered.get("prompt"), str):
            raise ValueError("Workflow renderer returned no prompt")
        return rendered["prompt"]
    raise ValueError(f"Unknown explicit workflow: {name}")


def autolith_worker(args, prompt: str, instructions: str, env: dict, artifacts: Path, schema, deadline: float):
    executable = require_host("autolith")
    session = uuid.uuid4().hex
    correction = False
    calls_used = 0
    aggregate = {"input_tokens": 0, "output_tokens": 0}
    original = prompt
    native_artifacts = []
    while True:
        remaining = deadline - time.monotonic()
        remaining_calls = args.max_turns - calls_used
        if remaining <= 0 or remaining_calls < 1:
            raise ValueError("Autolith verification is incomplete: cumulative time or model-call budget exhausted")
        execution = uuid.uuid4().hex
        job_file = Path(str(artifacts) + f".{execution}.job.sexp")
        result_file = Path(str(artifacts) + f".{execution}.result.sexp")
        native = Path(str(artifacts) + f".{execution}.autolith.native")
        job = [
            ":autolith-job", ":version", "1", ":id", sexp_string(execution),
            ":role", sexp_string(args.role), ":prompt", sexp_string(instructions + "\n\n" + prompt),
            ":input", "nil", ":timeout-seconds", str(max(1, int(remaining))),
            ":output-contract", schema_sexp(schema or {"type": "string"}),
        ]
        job_file.write_text("(" + " ".join(job) + ")\n")
        command = [
            executable, "--site-config-root", str(ROOT / "hosts/autolith"),
            "--permissions", "auto", *model_arguments("evaluator" if args.role == "evaluator" else "build"),
            "run-job", "--input", str(job_file), "--output", str(result_file),
        ]
        run_native(command, "", native, {**env, "WORKFLOW_HOST_MAX_TURNS": str(remaining_calls)}, remaining)
        if not result_file.is_file():
            raise ValueError("Autolith did not publish its terminal job result")
        envelope = autolith_result(result_file.read_text(), schema)
        used = envelope.get("provider_requests")
        if type(used) is not int or not 1 <= used <= remaining_calls:
            raise ValueError("Autolith returned unknown or excessive model-call usage")
        calls_used += used
        for key in aggregate:
            aggregate[key] += envelope["usage"].get(key, 0)
        native_artifacts.append({"job": str(job_file), "result": str(result_file), "output": str(native), "diagnostics": str(native) + ".stderr"})
        envelope.update(native_job=str(job_file), native_result=str(result_file),
                        native_artifacts=native_artifacts, usage=dict(aggregate), provider_requests=calls_used)
        if getattr(args, "action", "worker") != "prompt":
            return envelope, native
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("Autolith verification is incomplete: time budget exhausted")
        checked = subprocess.run(
            [sys.executable, str(ROOT / "scripts/host-bridge.py"), "event", "--event", "Stop"],
            input=json.dumps({"cwd": str(Path.cwd()), "session_id": session,
                              "stop_hook_active": correction, "last_assistant_message": envelope["result"]}),
            text=True, capture_output=True, check=True, timeout=remaining,
            env={**env, "WORKFLOW_HOST_WORKER": "0"},
        )
        gate = json.loads(checked.stdout)
        gate_file = Path(str(artifacts) + f".{execution}.verification.json")
        gate_file.write_text(checked.stdout)
        native_artifacts[-1]["verification"] = str(gate_file)
        action = gate.get("action") if isinstance(gate, dict) else None
        if action == "allow":
            return envelope, native
        if action != "repair":
            raise ValueError(f"Autolith completion has not been verified: {gate.get('reason') if isinstance(gate, dict) else 'invalid gate result'}")
        correction = True
        # The shared Stop state owns retry limits. Every job spends the original
        # invocation's remaining time and model allowance and retains its evidence.
        prompt = (original + "\n\nPrevious response:\n" + envelope["result"]
                  + "\n\nRequired verification failed. Correct the source and verify again:\n" + str(gate.get("reason", "")))


def pi_worker_command(role: str, instructions: str, *, ordinary: bool = False) -> list[str]:
    if ordinary:
        return [
            require_host("pi"), "--mode", "json", "--no-session",
            "--extension", str(ROOT), "--append-system-prompt", instructions,
            *model_arguments("evaluator" if role == "evaluator" else "build"),
        ]
    return [
        require_host("pi"), "--mode", "json", "--no-session", "--no-extensions",
        "--no-mcp", "--no-skills", "--no-prompt-templates",
        "--extension", str(ROOT / "hosts/pi/index.ts"),
        "--tools", ",".join(role_tools(role)),
        "--append-system-prompt", instructions,
        *model_arguments("evaluator" if role == "evaluator" else "build"),
    ]


def run_native(command: list[str], prompt: str, native: Path, env: dict, timeout: float) -> None:
    """Relay cancellation and timeouts to the complete native process group."""
    diagnostics = Path(str(native) + ".stderr")
    with native.open("w") as output, diagnostics.open("w") as errors:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=output, stderr=errors,
            env=env, text=True, start_new_session=True,
        )
        def interrupted(signum, _frame):
            terminate(process)
            raise SystemExit(128 + signum)

        handlers = {
            sig: signal.signal(sig, interrupted)
            for sig in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            process.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ValueError(f"Host worker timed out after {timeout:g} seconds") from None
        finally:
            terminate(process)
            for sig, previous in handlers.items():
                signal.signal(sig, previous)
    if process.returncode != 0:
        raise ValueError(f"Host worker exited {process.returncode}; native output: {native}; diagnostics: {diagnostics}")


def run_worker(args: argparse.Namespace, prompt: str) -> tuple[dict, Path]:
    deadline = time.monotonic() + args.timeout
    host = selected_host(args.host)
    if host == "claude":
        raise ValueError("Use the existing native Claude worker path")
    if args.max_turns < 1:
        raise ValueError("Worker turn and time limits must be positive")
    positive(args.timeout, "worker timeout")
    project = Path.cwd().resolve()
    role_tools(args.role)
    schema = json.loads(args.schema) if args.schema else None
    if schema is not None and not isinstance(schema, dict):
        raise ValueError("Worker schema must be a JSON object")
    artifacts = args.artifacts or project / ".claude/proofs/hosts" / uuid.uuid4().hex / "worker"
    artifacts.parent.mkdir(parents=True, exist_ok=True)
    native = Path(str(artifacts) + f".{host}.native")
    instructions = render_role(host, args.role, project)
    if getattr(args, "action", "worker") == "prompt":
        prompt = expand_workflow_prompt(host, prompt, project)
    env = {
        **os.environ,
        "WORKFLOW_HOST": host,
        "WORKFLOW_HOST_WORKER": "0" if getattr(args, "action", "worker") == "prompt" and host == "pi" else "1",
        "WORKFLOW_HOST_ROLE": args.role,
        "WORKFLOW_HOST_MAX_TURNS": str(args.max_turns),
        "CLAUDE_PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PROJECT_DIR": str(project),
    }
    if schema is not None:
        prompt += (
            "\n\nReturn only a JSON value satisfying this output contract. "
            "Do not wrap the result in Markdown. The controller validates it:\n"
            + json.dumps(schema, ensure_ascii=False)
        )
    if host == "pi":
        ordinary = getattr(args, "action", "worker") == "prompt"
        command = pi_worker_command(args.role, instructions, ordinary=ordinary)
        remaining = positive(deadline - time.monotonic(), "remaining worker time")
        run_native(command, prompt, native, env, remaining)
        envelope = pi_result(native.read_text(), schema, args.max_turns, require_verification=ordinary)
    else:
        envelope, native = autolith_worker(args, prompt, instructions, env, artifacts, schema, deadline)
    envelope["native_output"] = str(native)
    envelope["native_diagnostics"] = str(native) + ".stderr"
    return envelope, native


def stream_pi(native: Path) -> None:
    for line in native.read_text().split("\n"):
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") == "message_end" and event.get("message", {}).get("role") == "assistant":
            message = event["message"]
            content = []
            for item in message.get("content", []):
                if item.get("type") == "text":
                    content.append(item)
                elif item.get("type") == "toolCall":
                    content.append({"type": "tool_use", "name": item.get("name"), "input": item.get("arguments", {})})
            print(json.dumps({"type": "assistant", "message": {"model": message.get("model"), "content": content}}))


def run_session(args: argparse.Namespace) -> int:
    """Launch a visible native session; preserve newly created worktrees on exit."""
    host = selected_host(args.host)
    if host == "claude":
        raise ValueError("Use spawn-session.sh's native Claude path")
    executable = require_host(host)
    if args.resume and (args.role or args.name or args.worktree):
        raise ValueError("Resume restores its saved role and checkout")
    project = Path.cwd().resolve()
    role = args.role or "implementer"
    role_tools(role)
    prompt = args.prompt
    if args.goal:
        if prompt:
            raise ValueError("Choose a task prompt or a goal")
        prompt = args.goal
    if not args.resume and shutil.which("tmux") is None:
        raise ValueError("tmux is required for a visible role session")
    if not args.resume and not args.worktree and not os.environ.get("TMUX"):
        raise ValueError("For the current checkout, run inside tmux or pass --worktree")
    if args.worktree:
        result = subprocess.run(
            ["bash", str(ROOT / "skills/git-worktree/scripts/worktree-add.sh"), args.worktree],
            capture_output=True, text=True, check=True,
        )
        final = result.stdout.strip().split("\n")[-1]
        if not final.startswith("CREATED:"):
            raise ValueError("New sessions require a newly created worktree; existing checkout preserved")
        target = Path(final.removeprefix("CREATED:")).resolve(strict=True)
        for name in ("AGENTS.md", "project-commands.json", "project-environment.json"):
            source = project / ".claude" / name
            if source.is_file():
                (target / ".claude").mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target / ".claude" / name)
        project = target
    instructions = "" if args.resume else render_role(host, role, project)
    model = model_arguments("evaluator" if role == "evaluator" else "build") if not args.resume else []
    environment = {
        "RELAY_MODE": "0",
        "WORKFLOW_HOST": host,
        "WORKFLOW_HOST_WORKER": "0",
        "CLAUDE_PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PROJECT_DIR": str(project),
    }
    if not args.resume:
        environment["WORKFLOW_HOST_ROLE"] = role
    if host == "pi":
        command = [executable, "--extension", str(ROOT), *model]
        if args.resume:
            command.extend(["--session", str(pi_resume_path(args.resume))])
        else:
            command.extend(["--append-system-prompt", instructions])
            if args.name or args.worktree:
                command.extend(["--name", args.name or args.worktree])
            identifier = args.name or args.worktree or uuid.uuid4().hex
            if all(character.isalnum() or character in "._-" for character in identifier):
                command.extend(["--session-id", identifier])
        if prompt:
            command.append("/goal " + prompt if args.goal else prompt)
    else:
        command = [executable, "--site-config-root", str(ROOT / "hosts/autolith"), *model]
        if args.resume:
            command.extend(["resume", args.resume])
        environment["WORKFLOW_HOST_INITIAL_PROMPT"] = prompt
        environment["WORKFLOW_HOST_GOAL"] = prompt if args.goal else ""
        environment["WORKFLOW_HOST_SESSION_NAME"] = args.name or args.worktree or ""
    os.chdir(project)
    if args.resume:
        restored_environment = {**os.environ, **environment}
        restored_environment.pop("WORKFLOW_HOST_ROLE", None)
        restored_environment.pop("WORKFLOW_HOST_MAX_TURNS", None)
        restored_environment.pop("WORKFLOW_HOST_TASK_DEPTH", None)
        os.execvpe(command[0], command, restored_environment)
    # An existing tmux server does not inherit the current process environment.
    controls = ("WORKFLOW_HOST_ROLE", "WORKFLOW_HOST_MAX_TURNS", "WORKFLOW_HOST_TASK_DEPTH",
                "WORKFLOW_HOST_WORKER", "WORKFLOW_HOST_INITIAL_PROMPT", "WORKFLOW_HOST_GOAL", "WORKFLOW_HOST_SESSION_NAME")
    inherited = {key: value for key, value in os.environ.items()
                 if (key.startswith("WORKFLOW_") or key == "ANTHROPIC_MODEL") and key not in controls}
    effective = {**inherited, **environment}
    unset = [item for key in (*VARIABLES, *controls) if key not in effective for item in ("-u", key)]
    launch = ["env", *unset, *[f"{key}={value}" for key, value in effective.items()], *command]
    title = args.name or args.worktree or f"{host}-{role}"
    if os.environ.get("TMUX"):
        tmux = ["tmux", "new-window" if args.worktree else "split-window", "-c", str(project)]
        if args.worktree:
            tmux.extend(["-n", title])
        else:
            tmux.append("-h")
    else:
        tmux = ["tmux", "new-session", "-s", title, "-c", str(project)]
    return subprocess.run([*tmux, shlex.join(launch)], check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    session = commands.add_parser("session")
    session.add_argument("--host", choices=HOSTS, required=True)
    session.add_argument("--role")
    session.add_argument("--name")
    session.add_argument("--resume")
    session.add_argument("--worktree")
    session.add_argument("--goal")
    session.add_argument("--prompt", default="")
    for action in ("worker", "prompt"):
        command = commands.add_parser(action)
        command.add_argument("--host", choices=HOSTS, default=None)
        command.add_argument("--role", default="implementer")
        command.add_argument("--schema")
        command.add_argument("--max-turns", type=int, default=40)
        command.add_argument("--timeout", type=float, default=600)
        command.add_argument("--artifacts", type=Path)
        command.add_argument("--print", "-p", action="store_true")
        command.add_argument("--mode", choices=("json", "stream-json", "text"), default="text")
        command.add_argument("prompt", nargs="*")
    args = parser.parse_args()
    try:
        if args.action == "session":
            return run_session(args)
        host = selected_host(args.host)
        prompt = " ".join(args.prompt)
        if not sys.stdin.isatty():
            supplied = sys.stdin.read()
            prompt = supplied + ("\n\n" + prompt if prompt else "")
        if host == "claude":
            if args.action != "prompt":
                raise ValueError("Use native Claude for worker execution")
            command = [require_host(host), "--plugin-dir", str(ROOT)]
            if args.print or args.mode != "text":
                command.append("--print")
            if args.mode == "stream-json":
                command.extend(["--verbose", "--output-format", "stream-json"])
            command.extend(model_arguments("build"))
            command.append(prompt)
            os.execvp(command[0], command)
        envelope, native = run_worker(args, prompt)
        if args.action == "worker" or args.mode == "json":
            print(json.dumps(envelope, ensure_ascii=False, allow_nan=False))
        elif args.mode == "stream-json":
            if host == "pi":
                stream_pi(native)
            else:
                print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": envelope["result"]}]}}))
            print(json.dumps(envelope, ensure_ascii=False, allow_nan=False))
        else:
            print(envelope["result"])
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Host execution failed: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
