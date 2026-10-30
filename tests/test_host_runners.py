"""Native host transport must preserve the controller's acceptance contracts."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workflow_hosts import (  # noqa: E402
    autolith_result, pi_result, pi_resume_path, read_sexp, require_host, schema_sexp,
    selected_host, sexp_string, validate_schema, worker_command,
)

spec = importlib.util.spec_from_file_location("host_runner", ROOT / "scripts/host-runner.py")
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runner)

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["status", "summary"],
    "properties": {
        "status": {"type": "string", "enum": ["ready", "blocked"]},
        "summary": {"type": "string", "minLength": 1},
    },
}
PAYLOAD = {"status": "ready", "summary": "Fixture verified"}


def pi_events(*, payload=PAYLOAD, reason="stop", settled=False, turns=1) -> str:
    events = []
    for _ in range(turns):
        events.append({"type": "message_end", "message": {
            "role": "assistant", "model": "observed-pi-model", "stopReason": reason,
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "usage": {"input": 12, "output": 4},
        }})
    events.append({"type": "agent_settled", "aborted": settled})
    return "\n".join(json.dumps(item, ensure_ascii=False) for item in events)


def test_pi_reads_authoritative_messages_and_actual_model_usage():
    result = pi_result(pi_events(turns=2), SCHEMA, 3)
    assert result["structured_output"] == PAYLOAD
    assert result["modelUsage"] == {"observed-pi-model": {"inputTokens": 24, "outputTokens": 8}}
    assert result["num_turns"] == 2


def test_pi_jsonl_does_not_split_unicode_string_separators():
    payload = {**PAYLOAD, "summary": "First\u2028second\u2029third"}
    assert pi_result(pi_events(payload=payload), SCHEMA, 3)["structured_output"] == payload


def test_pi_successful_response_cannot_hide_a_blocked_stop_gate():
    record = {"type": "entry_appended", "entry": {
        "type": "custom", "customType": "agentic-coding-workflow:verification",
        "data": {"status": "blocked", "reason": "Verification failed"},
    }}
    raw = pi_events() + "\n" + json.dumps(record)
    with pytest.raises(ValueError, match="blocked completion"):
        pi_result(raw, SCHEMA, 3)
    with pytest.raises(ValueError, match="no successful"):
        pi_result(pi_events(), SCHEMA, 3, require_verification=True)
    record["entry"]["data"]["status"] = "passed"
    result = pi_result(pi_events() + "\n" + json.dumps(record), SCHEMA, 3, require_verification=True)
    assert result["structured_output"] == PAYLOAD


@pytest.mark.parametrize("raw", [
    pi_events(reason="error"), pi_events(reason="aborted"), pi_events(reason="length"),
    pi_events(reason="toolUse"), pi_events(settled=True),
    pi_events(turns=4), pi_events(payload={"status": "ready"}),
    pi_events(payload={**PAYLOAD, "unexpected": True}), "{}", "{broken}", "[]",
])
def test_pi_failures_cannot_be_normalized_as_success(raw: str):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        pi_result(raw, SCHEMA, 3)


@pytest.mark.parametrize("raw", [
    '#.(delete-file "important")', '#1=(:object ("loop" #1#))',
    '(:object ("x" 1)) (:object ("x" 2))',
    '(arbitrary:execute "command")', '(a . b)', '("unterminated)',
    '(' * 66 + ')' * 66,
])
def test_autolith_reader_rejects_executable_ambiguous_or_unbounded_forms(raw: str):
    with pytest.raises(ValueError):
        read_sexp(raw)


def autolith_envelope(result='(:object ("status" "ready") ("summary" "Fixture verified"))', status=":succeeded"):
    return f'(:autolith-job-result :version 1 :id "job" :status {status} :result {result} :usage (:input-tokens 12 :output-tokens 4 :provider-requests 2) :trace-id "trace")'


def test_autolith_native_tags_preserve_false_null_empty_array_and_strings():
    value = autolith_result(autolith_envelope('(:object ("false" nil) ("null" :null) ("array" (:array)) ("string" "nil"))'), None)
    assert value["structured_output"] == {"false": False, "null": None, "array": [], "string": "nil"}
    assert value["usage"] == {"input_tokens": 12, "output_tokens": 4}
    assert value["modelUsage"] == {}
    assert value["model_provenance"] == "unavailable_in_job_envelope"
    assert value["trace_id"] == "trace"


@pytest.mark.parametrize("raw", [
    autolith_envelope(status=":failed"), autolith_envelope(status='"succeeded"'),
    autolith_envelope().replace(":version 1", ":version t"),
    autolith_envelope().replace(":version 1", ":version 1 :version 1"),
    autolith_envelope('(:object ("status" "ready") ("status" "ready"))'),
    autolith_envelope('(:object ("status" "ready") ("summary" ""))'),
    autolith_envelope('(:object ("status" "unknown") ("summary" "text"))'),
    autolith_envelope().replace(":input-tokens 12", ":input-tokens -1"),
])
def test_autolith_failure_or_invalid_contract_cannot_accept(raw: str):
    with pytest.raises(ValueError):
        autolith_result(raw, SCHEMA)


def test_native_schema_projection_uses_documented_data_only_dialect():
    projected = schema_sexp(SCHEMA)
    assert ":additional-properties nil" in projected
    assert '(:type :string :enum ("ready" "blocked"))' in projected
    read_sexp(projected)
    original = 'quotes " slash \\ newline\n$(touch injected)'
    assert read_sexp(sexp_string(original)) == original


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "2"])
def test_numeric_schema_does_not_accept_booleans_or_nonfinite_numbers(value):
    with pytest.raises(ValueError):
        validate_schema(value, {"type": "number"})


def test_host_selection_is_explicit_and_never_falls_back(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_HOST", "pi")
    assert selected_host() == "pi"
    assert selected_host("claude") == "claude"
    with pytest.raises(ValueError, match="Unknown"):
        selected_host("other")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ValueError, match="not installed"):
        require_host("pi")
    command = worker_command("pi", "evaluator", SCHEMA, max_turns=25, timeout=30)
    assert command[command.index("--host") + 1] == "pi"
    assert command[command.index("--role") + 1] == "evaluator"
    assert json.loads(command[command.index("--schema") + 1]) == SCHEMA
    assert "claude" not in command


def test_pi_resume_requires_one_saved_session_and_preserves_its_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    for name in ("feature-a", "feature-b"):
        path = tmp_path / "sessions/project" / f"time_{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "session", "id": name, "cwd": "/original/worktree"}) + "\n")
    assert pi_resume_path("feature-a") == tmp_path / "sessions/project/time_feature-a.jsonl"
    with pytest.raises(ValueError, match="ambiguous"):
        pi_resume_path("feature")
    with pytest.raises(ValueError, match="unavailable"):
        pi_resume_path("missing")
    with pytest.raises(ValueError, match="does not exist"):
        pi_resume_path("missing.jsonl")


@pytest.fixture
def fake_hosts(tmp_path: Path, monkeypatch):
    binary = tmp_path / "bin"
    binary.mkdir()
    code = '''
import json, os, pathlib, sys
record = {"argv": sys.argv[1:], "cwd": str(pathlib.Path.cwd()), "role": os.environ.get("WORKFLOW_HOST_ROLE"), "worker": os.environ.get("WORKFLOW_HOST_WORKER"), "relay": os.environ.get("RELAY_MODE"), "stdin": sys.stdin.read()}
pathlib.Path(os.environ["TEST_HOST_RECORD"]).write_text(json.dumps(record))
if os.environ.get("TEST_HOST_EXIT"):
    raise SystemExit(int(os.environ["TEST_HOST_EXIT"]))
if pathlib.Path(sys.argv[0]).name == "pi":
    print(os.environ["TEST_PI_EVENTS"])
else:
    text = pathlib.Path(sys.argv[sys.argv.index("--input") + 1]).read_text()
    assert ":input nil" in text and ":output-contract" in text
    if not os.environ.get("TEST_AUTOLITH_NO_RESULT"):
        pathlib.Path(sys.argv[sys.argv.index("--output") + 1]).write_text(os.environ["TEST_AUTOLITH_RESULT"])
'''
    for host in ("pi", "autolith"):
        path = binary / host
        path.write_text(f"#!{sys.executable}\n" + code)
        path.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("TEST_HOST_RECORD", str(tmp_path / "record.json"))
    monkeypatch.setenv("TEST_PI_EVENTS", pi_events())
    monkeypatch.setenv("TEST_AUTOLITH_RESULT", autolith_envelope())
    monkeypatch.setenv("RELAY_MODE", "1")
    monkeypatch.setattr(runner, "render_role", lambda *args: "Rendered role instructions")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("host", ["pi", "autolith"])
def test_real_runner_process_boundary_preserves_role_cwd_and_contract(host: str, fake_hosts: Path):
    args = argparse.Namespace(host=host, role="evaluator", schema=json.dumps(SCHEMA), max_turns=25, timeout=3, artifacts=fake_hosts / ".claude/worker")
    envelope, native = runner.run_worker(args, "Review the candidate")
    assert envelope["structured_output"] == PAYLOAD
    assert envelope["host"] == host
    assert native.is_file()
    record = json.loads((fake_hosts / "record.json").read_text())
    assert record["cwd"] == str(fake_hosts)
    assert record["role"] == "evaluator"
    assert record["worker"] == "1"
    assert record["relay"] == "1"
    assert "--dangerously-skip-permissions" not in record["argv"]
    if host == "pi":
        assert "--no-extensions" in record["argv"]
        assert "--no-mcp" in record["argv"]
        assert record["argv"][record["argv"].index("--tools") + 1] == "read,grep,find,ls"
        assert "Rendered role instructions" in record["argv"]
        assert "Review the candidate" in record["stdin"]
    else:
        assert record["argv"][record["argv"].index("--permissions") + 1] == "auto"
        assert record["argv"][record["argv"].index("--site-config-root") + 1] == str(ROOT / "hosts/autolith")


def test_nonzero_native_exit_rejects_valid_looking_output(fake_hosts: Path, monkeypatch):
    monkeypatch.setenv("TEST_HOST_EXIT", "7")
    args = argparse.Namespace(host="pi", role="evaluator", schema=json.dumps(SCHEMA), max_turns=25, timeout=3, artifacts=fake_hosts / ".claude/worker")
    with pytest.raises(ValueError, match="exited 7"):
        runner.run_worker(args, "Review")


def test_existing_autolith_result_is_never_reused(fake_hosts: Path, monkeypatch):
    output = fake_hosts / ".claude/worker"
    output.parent.mkdir()
    Path(str(output) + ".result.sexp").write_text(autolith_envelope())
    monkeypatch.setenv("TEST_AUTOLITH_NO_RESULT", "1")
    args = argparse.Namespace(host="autolith", role="evaluator", schema=json.dumps(SCHEMA), max_turns=25, timeout=3, artifacts=output)
    with pytest.raises(ValueError, match="did not publish"):
        runner.run_worker(args, "Review")


def test_autolith_corrections_keep_original_call_budget_and_shared_stop_state(fake_hosts: Path, monkeypatch):
    gates, allowances = [], []
    native = runner.run_native

    def record_native(command, prompt, output, environment, timeout):
        allowances.append(int(environment["WORKFLOW_HOST_MAX_TURNS"]))
        return native(command, prompt, output, environment, timeout)

    def stop(command, **options):
        gates.append(json.loads(options["input"]))
        return subprocess.CompletedProcess(command, 0, json.dumps({"action": "repair" if len(gates) == 1 else "allow", "reason": "Fix the fixture"}), "")

    monkeypatch.setattr(runner, "run_native", record_native)
    monkeypatch.setattr(runner.subprocess, "run", stop)
    args = argparse.Namespace(action="prompt", host="autolith", role="implementer", schema=json.dumps(SCHEMA), max_turns=5, timeout=3, artifacts=fake_hosts / ".claude/worker")
    envelope, _ = runner.run_worker(args, "Implement the fixture")
    assert allowances == [5, 3]
    assert [gate["stop_hook_active"] for gate in gates] == [False, True]
    assert gates[0]["session_id"] == gates[1]["session_id"]
    assert envelope["provider_requests"] == 4
    assert len(envelope["native_artifacts"]) == 2
    assert envelope["usage"] == {"input_tokens": 24, "output_tokens": 8}


@pytest.mark.parametrize("host", ["pi", "autolith"])
def test_headless_explicit_workflows_expand_and_preserve_invocation_controls(host: str):
    prompt = runner.expand_workflow_prompt(host, "/test fixture-scope", ROOT)
    assert "Detect Test Runner" in prompt
    assert "fixture-scope" in prompt
    assert "${CLAUDE_PLUGIN_ROOT}" not in prompt
    with pytest.raises(ValueError, match="model only"):
        runner.expand_workflow_prompt(host, "/pr-reviewer", ROOT)
    with pytest.raises(ValueError, match="Unknown explicit"):
        runner.expand_workflow_prompt(host, "/unknown-workflow", ROOT)


def test_new_tmux_session_clears_stale_worker_and_absent_model_settings(fake_hosts: Path, monkeypatch):
    calls = []
    monkeypatch.setenv("TMUX", "existing")
    monkeypatch.setenv("WORKFLOW_HOST_MAX_TURNS", "999")
    monkeypatch.setenv("WORKFLOW_HOST_TASK_DEPTH", "99")
    monkeypatch.delenv("WORKFLOW_MODEL", raising=False)
    monkeypatch.setattr(runner.shutil, "which", lambda command: str(fake_hosts / "bin" / command))

    def launch(command, **options):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", launch)
    args = argparse.Namespace(host="pi", role="implementer", name="feature", resume=None, worktree=None, goal=None, prompt="Implement")
    assert runner.run_session(args) == 0
    launch_args = shlex.split(calls[0][-1])
    for key in ("WORKFLOW_MODEL", "WORKFLOW_HOST_MAX_TURNS", "WORKFLOW_HOST_TASK_DEPTH"):
        position = launch_args.index(key)
        assert launch_args[position - 1] == "-u"
    assert "WORKFLOW_HOST_WORKER=0" in launch_args
    assert "WORKFLOW_HOST_ROLE=implementer" in launch_args


@pytest.mark.parametrize("flag,value", [
    ("--tools", "Read"), ("--disallowedTools", "Bash"), ("--settings", "{}"),
    ("--agent", "evaluator"), ("--permission-mode", "dontAsk"),
    ("--mcp-config", "{}"), ("--strict-mcp-config", None),
])
def test_non_claude_pipeline_rejects_untranslated_restrictions(tmp_path: Path, flag: str, value: str | None):
    command = ["bash", "-c", 'source "$1"; shift; run_claude_pipeline prompt log trace 0 processor "$@"',
               "pipeline-test", str(ROOT / "scripts/lib/claude-runner.sh"), flag]
    if value is not None:
        command.append(value)
    result = subprocess.run(command, cwd=tmp_path, env={**os.environ, "WORKFLOW_HOST": "pi"},
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "Unsupported capability or permission flag" in result.stderr
    assert not (tmp_path / "log").exists()


@pytest.mark.parametrize("role,key", [("implementer", "WORKFLOW_BUILD_MODEL"), ("evaluator", "WORKFLOW_EVALUATOR_MODEL")])
def test_pipeline_explicit_model_wins_over_inherited_role_model(tmp_path: Path, role: str, key: str):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    native = scripts / "host-runner.py"
    native.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(ROOT / 'scripts')!r})\n"
        "from workflow_models import selection\n"
        f"print(json.dumps(selection({'evaluator' if role == 'evaluator' else 'build'!r})))\n"
    )
    processor = tmp_path / "processor"
    processor.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.write(sys.stdin.read())\n")
    processor.chmod(0o755)
    command = ["bash", "-c",
               'source "$1"; _WORKFLOW_ROOT="$2"; shift 2; run_claude_pipeline prompt log trace 0 ./processor "$@"',
               "pipeline-test", str(ROOT / "scripts/lib/claude-runner.sh"), str(tmp_path),
               "--model", "explicit-model"]
    if role == "evaluator":
        command.append("--restricted")
    result = subprocess.run(command, cwd=tmp_path, env={**os.environ, "WORKFLOW_HOST": "pi", key: "inherited-model"},
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "log").read_text())["requested"] == "explicit-model"
