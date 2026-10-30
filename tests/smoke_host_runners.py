#!/usr/bin/env python3
"""Exercise installed hosts against a localhost fixture, without paid inference.

The fixture exercises each host's real provider protocol and tool projection.
It establishes transport and gating behavior, not model effectiveness.
"""

import argparse
from contextlib import contextmanager
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workflow_execution import source_state, timestamp, write_json  # noqa: E402
from workflow_hosts import pi_result, require_host, sexp_string  # noqa: E402

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["status", "summary"],
    "properties": {
        "status": {"type": "string", "enum": ["ready", "blocked"]},
        "summary": {"type": "string", "minLength": 1},
    },
}
PAYLOAD = {"status": "ready", "summary": "Local fixture transport exercised"}


@contextmanager
def fixture_provider(host: str, output: object, *, repair: bool = False, request_counter: Path | None = None):
    calls = []

    class Fixture(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(request)
            if request_counter is not None:
                request_counter.write_text(str(len(calls)))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if repair and host == "autolith" and len(calls) in (2, 3):
                names = [tool.get("function", {}).get("name", "") for tool in request.get("tools", [])]
                operation = "read" if len(calls) == 2 else "edit"
                name = next((name for name in names if "resource" in name and name.endswith("__" + operation)), "resource__" + operation)
                arguments = {"uri": "workspace:repaired"}
                if operation == "edit":
                    feedback = "\n".join(str(message.get("content", "")) for message in request.get("messages", []) if message.get("role") == "tool")
                    revision = re.search(r"Revision:\s*([^\s]+)", feedback)
                    arguments.update({"base-revision": revision[1] if revision else "missing-revision",
                                      "operations": [{"op": "replace-empty", "content": "repaired\n"}]})
                delta = {"tool_calls": [{"index": 0, "id": f"fixture-{len(calls)}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}
                finish = "tool_calls"
            elif repair and len(calls) == 2:
                names = [tool.get("function", {}).get("name", "") for tool in request.get("tools", [])]
                name = "bash" if host == "pi" else next((name for name in names if "shell" in name and "run" in name), "shell__run")
                arguments = json.dumps({"command": "touch repaired"})
                delta = {"tool_calls": [{"index": 0, "id": f"fixture-{len(calls)}", "type": "function", "function": {"name": name, "arguments": arguments}}]}
                finish = "tool_calls"
            elif host == "autolith":
                tools = request.get("tools", [])
                names = [tool.get("function", {}).get("name", "") for tool in tools]
                name = next((name for name in names if "yield" in name and "submit" in name), "yield__submit")
                arguments = json.dumps({"status": "success", "data": output})
                delta = {"tool_calls": [{"index": 0, "id": f"fixture-{len(calls)}", "type": "function", "function": {"name": name, "arguments": arguments}}]}
                finish = "tool_calls"
            else:
                delta = {"role": "assistant", "content": output if isinstance(output, str) else json.dumps(output)}
                finish = "stop"
            for content, reason, usage in (
                (delta, None, None),
                ({}, finish, {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}),
            ):
                event = {
                    "id": "fixture", "object": "chat.completion.chunk", "created": 1,
                    "model": "fixture-model", "choices": [{"index": 0, "delta": content, "finish_reason": reason}],
                }
                if usage is not None:
                    event["usage"] = usage
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, *_args):
            pass

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fixture) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/v1", calls
        finally:
            server.shutdown()
            thread.join(timeout=2)


def host_environment(host: str, directory: Path, endpoint: str) -> dict:
    # Only the fixture's isolated credential/configuration roots are visible.
    environment = {
        **os.environ,
        "WORKFLOW_HOST": host,
        "WORKFLOW_NOTIFY": "false",
        "WORKFLOW_MODEL": "workflow-fixture/fixture-model",
        "WORKFLOW_BUILD_MODEL": "workflow-fixture/fixture-model",
        "WORKFLOW_EVALUATOR_MODEL": "workflow-fixture/fixture-model",
        "PI_CODING_AGENT_DIR": str(directory / "pi-agent"),
        "XDG_CONFIG_HOME": str(directory / "config"),
        "XDG_STATE_HOME": str(directory / "state"),
        "XDG_CACHE_HOME": str(directory / "cache"),
        "XDG_DATA_HOME": str(ROOT / ".claude/host-tools/autolith-smoke-data"),
        "AUTOLITH_ONBOARDING": "off",
    }
    for key in ("WORKFLOW_HOST_ROLE", "WORKFLOW_HOST_MAX_TURNS", "WORKFLOW_HOST_WORKER", "RELAY_MODE"):
        environment.pop(key, None)
    if host == "pi":
        agent = Path(environment["PI_CODING_AGENT_DIR"])
        agent.mkdir(parents=True)
        model = {
            "id": "fixture-model", "name": "Local fixture", "reasoning": False,
            "input": ["text"], "contextWindow": 128000, "maxTokens": 4096,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        }
        (agent / "models.json").write_text(json.dumps({"providers": {"workflow-fixture": {
            "baseUrl": endpoint, "api": "openai-completions", "apiKey": "fixture-only", "models": [model],
        }}}))
        (agent / "settings.json").write_text(json.dumps({"defaultProvider": "workflow-fixture", "defaultModel": "fixture-model", "quietStartup": True}))
    else:
        config = Path(environment["XDG_CONFIG_HOME"]) / "autolith"
        config.mkdir(parents=True)
        (config / "init.lisp").write_text(
            '(in-package #:autolith)\n'
            '(register-openai-compatible-provider :name "workflow-fixture" '
            f':endpoint {sexp_string(endpoint + "/chat/completions")} :models \'("fixture-model"))\n'
        )
        state = Path(environment["XDG_STATE_HOME"]) / "autolith"
        state.mkdir(parents=True)
        (state / "api-keys.sexp").write_text('(:api-keys :version 1 :providers ((:provider :provider-name "workflow-fixture" :api-key "fixture-only")))\n')
    return environment


def project_fixture(directory: Path, passes: bool, repair: bool = False) -> Path:
    project = directory / "project with spaces"
    project.mkdir()
    (project / ".gitignore").write_text(".claude/\n")
    (project / "source.py").write_text("VALUE = 1\n")
    for arguments in (
        ["init", "--quiet", "-b", "main"], ["config", "user.name", "Host fixture"],
        ["config", "user.email", "fixture@example.invalid"], ["add", "."], ["commit", "--quiet", "-m", "Fixture"],
    ):
        subprocess.run(["git", *arguments], cwd=project, check=True, capture_output=True)
    (project / ".claude").mkdir()
    test = "test -f repaired" if repair else "true" if passes else "false"
    (project / ".claude/project-commands.json").write_text(json.dumps({"lint": "true", "test": test}))
    return project


def scenario(host: str, name: str, output_dir: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"workflow-{host}-{name}-") as temporary:
        directory = Path(temporary)
        output = PAYLOAD if name == "worker-evaluator" else "Fixture response"
        project = project_fixture(directory, passes=name not in ("ordinary-failure", "ordinary-budget"), repair=name == "ordinary-repair")
        request_counter = directory / "provider-request-count"
        notification_log = directory / "desktop-notifications.jsonl"
        with fixture_provider(host, output, repair=name == "ordinary-repair", request_counter=request_counter) as (endpoint, calls):
            environment = host_environment(host, directory, endpoint)
            command = [
                sys.executable, str(ROOT / "scripts/host-runner.py"),
                "worker" if name == "worker-evaluator" else "prompt", "--host", host,
                "--role", "evaluator" if name == "worker-evaluator" else "implementer",
                "--max-turns", "2" if name == "ordinary-budget" else "8", "--timeout", "45",
                "--artifacts", str(output_dir / f"{host}-{name}"),
            ]
            if name == "worker-evaluator":
                command.extend(["--schema", json.dumps(SCHEMA)])
            if name == "direct-command":
                command = [require_host("pi"), "--mode", "json", "--no-session", "--extension", str(ROOT),
                           "--model", "workflow-fixture/fixture-model"]
            if name == "deferred-notification":
                notifications = directory / "notification-bin"
                notifications.mkdir()
                sender = notifications / "osascript"
                sender.write_text(
                    '#!/usr/bin/env python3\n'
                    'import json, os, sys\nfrom pathlib import Path\n'
                    'record = {"arguments": sys.argv[1:], "provider_calls": int(Path(os.environ["WORKFLOW_FIXTURE_REQUEST_COUNT"]).read_text())}\n'
                    'with Path(os.environ["WORKFLOW_FIXTURE_NOTIFICATION_LOG"]).open("a") as stream: stream.write(json.dumps(record) + "\\n")\n'
                )
                sender.chmod(0o755)
                continuation = directory / "continue-after-settled.ts"
                continuation.write_text(
                    'export default function (pi) {\n'
                    '  let queued = false;\n'
                    '  pi.on("agent_settled", () => {\n'
                    '    if (queued) return;\n'
                    '    queued = true;\n'
                    '    pi.sendUserMessage("First deferred continuation");\n'
                    '    pi.sendUserMessage("Second deferred continuation");\n'
                    '  });\n'
                    '}\n'
                )
                environment.update({
                    "PATH": str(notifications) + os.pathsep + environment["PATH"],
                    "WORKFLOW_NOTIFY": "true",
                    "WORKFLOW_FIXTURE_REQUEST_COUNT": str(request_counter),
                    "WORKFLOW_FIXTURE_NOTIFICATION_LOG": str(notification_log),
                })
                # Load the continuation first: it queues native deferred work
                # before the adapter's notification-only settled callback.
                command = [require_host("pi"), "--mode", "json", "--no-session",
                           "--extension", str(continuation), "--extension", str(ROOT),
                           "--model", "workflow-fixture/fixture-model"]
            prompt = "/test fixture-scope" if name in ("ordinary-command", "direct-command") else "Exercise only the local fixture transport."
            result = subprocess.run(command, input=prompt, cwd=project,
                                    env=environment, capture_output=True, text=True, timeout=60)
        stem = output_dir / f"{host}-{name}"
        Path(str(stem) + ".stdout").write_text(result.stdout)
        Path(str(stem) + ".stderr").write_text(result.stderr)
        names = [tool.get("function", {}).get("name", "") for request in calls for tool in request.get("tools", [])]
        unique_tools = sorted(set(names))
        issues = []
        if name in ("ordinary-failure", "ordinary-budget"):
            if result.returncode == 0:
                issues.append("Failing project checks were accepted")
            if name == "ordinary-failure" and "verif" not in result.stderr.lower():
                issues.append("Failure did not report incomplete verification")
        elif result.returncode != 0:
            issues.append(f"Host runner exited {result.returncode}")
        if not calls:
            issues.append("No request reached the localhost fixture")
        if name == "ordinary-failure" and len(calls) != 4:
            issues.append("Shared three-attempt verification cap was not preserved")
        if name == "ordinary-budget" and len(calls) != 2:
            issues.append("Cumulative model-call budget was not enforced")
        if name == "ordinary-repair" and not (project / "repaired").is_file():
            issues.append("Native correction did not exercise the real write/tool path")
        if name in ("ordinary-command", "direct-command") and calls:
            context = json.dumps(calls[0].get("messages", []))
            if "Detect Test Runner" not in context or "fixture-scope" not in context:
                issues.append("Explicit /test was not expanded into the native provider prompt")
        if name == "direct-command" and result.returncode == 0:
            try:
                pi_result(result.stdout, None, 40, require_verification=True)
            except ValueError as error:
                issues.append(str(error))
        if name == "deferred-notification":
            notifications = [json.loads(line) for line in notification_log.read_text().splitlines()] if notification_log.exists() else []
            if len(calls) != 3:
                issues.append(f"Expected three native provider requests, observed {len(calls)}")
            if len(notifications) != 1 or notifications[0].get("provider_calls") != 3:
                issues.append(f"Readiness was sent before deferred work drained, or was omitted/duplicated: {notifications}")
            if result.returncode == 0:
                try:
                    pi_result(result.stdout, None, 40, require_verification=True)
                except ValueError as error:
                    issues.append(str(error))
            write_json(Path(str(stem) + ".notifications.json"), notifications)
        if name == "worker-evaluator" and result.returncode == 0:
            envelope = json.loads(result.stdout)
            if envelope.get("structured_output") != PAYLOAD:
                issues.append("Native result did not preserve the structured worker contract")
            if any(re.search(r"(?:^|[._])(?:write|edit|bash|shell|task|self|lisp|mcp)(?:[._]|$)", tool) for tool in names):
                issues.append("Evaluator was exposed to tools outside its read-only role")
            if host == "pi" and envelope.get("modelUsage", {}).get("fixture-model", {}).get("inputTokens") != 12:
                issues.append("Pi lost observed model/token provenance")
            if host == "autolith" and envelope.get("usage", {}).get("input_tokens") != 12:
                issues.append("Autolith lost native usage counters")
        checked = {"host": host, "scenario": name, "command": command, "exit_code": result.returncode,
                   "provider_calls": len(calls), "exposed_tools": unique_tools, "issues": issues,
                   "outcome": "passed" if not issues else "failed"}
        write_json(Path(str(stem) + ".result.json"), checked)
        return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("pi", "autolith", "all"), default="all")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = (args.output_dir or ROOT / ".claude/proofs/hosts" / f"run-{uuid.uuid4().hex[:12]}").resolve()
    output.mkdir(parents=True, exist_ok=True)
    before = source_state(ROOT)
    records = []
    failure = None
    try:
        hosts = ("pi", "autolith") if args.host == "all" else (args.host,)
        for host in hosts:
            require_host(host)
            for name in ("worker-evaluator", "ordinary-success", "ordinary-command", "ordinary-repair", "ordinary-failure", "ordinary-budget"):
                record = scenario(host, name, output)
                records.append(record)
                print(f"{host} {name}: {record['outcome']}", flush=True)
            if host == "pi":
                for name in ("direct-command", "deferred-notification"):
                    record = scenario(host, name, output)
                    records.append(record)
                    print(f"{host} {name}: {record['outcome']}", flush=True)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        failure = str(error)
    after = source_state(ROOT)
    passed = not failure and records and all(item["outcome"] == "passed" for item in records) and before == after
    summary = {"outcome": "passed" if passed else "failed", "started_source": before, "finished_source": after,
               "source_unchanged": before == after, "finished_at": timestamp(), "failure": failure,
               "evidence_kind": "installed-host-local-fixture", "paid_inference": False, "scenarios": records}
    write_json(output / "summary.json", summary)
    print(output / "summary.json")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
