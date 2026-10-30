#!/usr/bin/env python3
"""Host selection, bounded data decoding, and validated worker results.

The controller's acceptance contract is independent of the host transport.
Native host output is retained beside the normalized result for inspection.
"""

import json
import math
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("claude", "pi", "autolith")
MAX_RESULT_BYTES = 16 * 1024 * 1024


def selected_host(value: str | None = None) -> str:
    host = value if value is not None else os.environ.get("WORKFLOW_HOST", "claude")
    if host not in HOSTS:
        raise ValueError(f"Unknown workflow host: {host!r}; choose {', '.join(HOSTS)}")
    return host


def require_host(host: str) -> str:
    selected_host(host)
    executable = shutil.which(host)
    if executable is None:
        raise ValueError(f"Requested host {host!r} is not installed or is not on PATH")
    return executable


def pi_resume_path(reference: str) -> Path:
    """Resolve a saved file before launch so Pi restores its original checkout.

    Pi offers to fork cross-project ID matches. Passing the saved file instead
    requests its native resume behavior, including the stored working directory.
    """
    direct = Path(reference).expanduser()
    if direct.is_file():
        return direct.resolve()
    if "/" in reference or "\\" in reference or reference.endswith(".jsonl"):
        raise ValueError(f"Pi session file does not exist: {reference}")
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi/agent"))
    roots = {agent / "sessions"}
    override = os.environ.get("PI_CODING_AGENT_SESSION_DIR")
    if override:
        roots.add(Path(override).expanduser())
    settings = agent / "settings.json"
    if settings.is_file():
        configured = json.loads(settings.read_text()).get("sessionDir")
        if isinstance(configured, str) and configured:
            roots.add(Path(configured).expanduser())
    candidates = {}
    for directory in roots:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.jsonl"):
            try:
                with path.open() as stream:
                    header = json.loads(stream.readline(65536))
            except (OSError, UnicodeError, ValueError):
                continue
            if isinstance(header, dict) and header.get("type") == "session" and isinstance(header.get("id"), str):
                identifier = header["id"]
                if identifier.startswith(reference):
                    candidates[path.resolve()] = identifier
    exact = [path for path, identifier in candidates.items() if identifier == reference]
    matches = exact or list(candidates)
    if len(matches) != 1:
        raise ValueError(f"Pi session is {'ambiguous' if matches else 'unavailable'}: {reference}; supply its exact JSONL path")
    return matches[0]


def worker_command(
    host: str,
    role: str,
    schema: dict,
    *,
    max_turns: int = 40,
    timeout: float = 600,
    output: Path | None = None,
) -> list[str]:
    selected_host(host)
    if host == "claude":
        raise ValueError("The native Claude runner owns its existing invocation")
    result = [
        sys.executable,
        str(ROOT / "scripts/host-runner.py"),
        "worker",
        "--host",
        host,
        "--role",
        role,
        "--schema",
        json.dumps(schema, separators=(",", ":")),
        "--max-turns",
        str(max_turns),
        "--timeout",
        str(timeout),
    ]
    if output is not None:
        result.extend(["--artifacts", str(output)])
    return result


def validate_schema(value: object, schema: dict, path: str = "result") -> None:
    """Check the JSON-schema subset used by the existing worker contracts."""
    kind = schema.get("type")
    valid_type = {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "number": lambda: type(value) in (int, float) and math.isfinite(value),
        "integer": lambda: type(value) is int,
        "boolean": lambda: type(value) is bool,
        "null": lambda: value is None,
    }
    if kind not in valid_type or not valid_type[kind]():
        raise ValueError(f"{path} does not have required type {kind!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is outside its allowed values")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", ())) - set(value)
        if missing:
            raise ValueError(f"{path} is missing fields: {', '.join(sorted(missing))}")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"{path} has unexpected fields")
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], f"{path}.{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{path} contains too few items")
        for index, item in enumerate(value):
            if "items" in schema:
                validate_schema(item, schema["items"], f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{path} is too short")
    elif type(value) in (int, float):
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ValueError(f"{path} is outside its numeric bounds")


def pi_result(
    raw: str, schema: dict | None, max_turns: int, *, require_verification: bool = False
) -> dict:
    if len(raw.encode("utf-8")) > MAX_RESULT_BYTES:
        raise ValueError("Pi output exceeds the worker result limit")
    messages = []
    settled = None
    verification = None
    for line in raw.split("\n"):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("Pi emitted a non-object event")
        if event.get("type") == "extension_error":
            raise ValueError("Pi worker extension failed")
        if event.get("type") == "message_end":
            message = event.get("message")
            if isinstance(message, dict) and message.get("role") == "assistant":
                messages.append(message)
        if event.get("type") == "agent_settled":
            settled = event
        if event.get("type") == "entry_appended":
            entry = event.get("entry")
            if isinstance(entry, dict) and entry.get("customType") == "agentic-coding-workflow:verification":
                verification = entry.get("data")
    if not isinstance(settled, dict) or settled.get("aborted") is not False:
        raise ValueError("Pi did not settle successfully")
    if not messages or len(messages) > max_turns:
        raise ValueError("Pi returned no assistant result or exhausted its turn limit")
    if isinstance(verification, dict) and verification.get("status") == "blocked":
        raise ValueError(f"Pi verification blocked completion: {verification.get('reason', '')}")
    if require_verification and (not isinstance(verification, dict) or verification.get("status") != "passed"):
        raise ValueError("Pi returned no successful workflow verification record")
    final = messages[-1]
    if final.get("stopReason") != "stop":
        raise ValueError(f"Pi ended without a completed response: {final.get('stopReason')}")
    content = final.get("content")
    if not isinstance(content, list):
        raise ValueError("Pi returned invalid assistant content")
    text = "\n".join(
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    )
    payload = json.loads(text) if schema is not None else None
    if schema is not None:
        validate_schema(payload, schema)
    models = {}
    for message in messages:
        model = message.get("model")
        if isinstance(model, str) and model:
            usage = message.get("usage")
            aggregate = models.setdefault(model, {"inputTokens": 0, "outputTokens": 0})
            if isinstance(usage, dict):
                for source, target in (("input", "inputTokens"), ("output", "outputTokens")):
                    amount = usage.get(source)
                    if type(amount) in (int, float) and math.isfinite(amount) and amount >= 0:
                        aggregate[target] += amount
    return {
        "type": "result",
        "is_error": False,
        "subtype": "success",
        "structured_output": payload,
        "result": text,
        "modelUsage": models,
        "host": "pi",
        "num_turns": len(messages),
    }


class Keyword(str):
    """An admitted Lisp keyword, distinct from a string value."""


def read_sexp(raw: str) -> object:
    """Decode one bounded data form. Reader macros and arbitrary symbols fail."""
    if len(raw.encode("utf-8")) > MAX_RESULT_BYTES:
        raise ValueError("Autolith result exceeds the data limit")
    position, nodes = 0, 0

    def skip() -> None:
        nonlocal position
        while position < len(raw) and raw[position].isspace():
            position += 1

    def form(depth: int = 0) -> object:
        nonlocal position, nodes
        nodes += 1
        if depth > 64 or nodes > 262144:
            raise ValueError("Autolith data nesting or node limit exceeded")
        skip()
        if position >= len(raw):
            raise ValueError("Unexpected end of Autolith data")
        char = raw[position]
        if char == "(":
            position += 1
            items = []
            while True:
                skip()
                if position >= len(raw):
                    raise ValueError("Unterminated Autolith list")
                if raw[position] == ")":
                    position += 1
                    return items
                items.append(form(depth + 1))
        if char == '"':
            position += 1
            chars = []
            while position < len(raw):
                char = raw[position]
                position += 1
                if char == '"':
                    return "".join(chars)
                if char == "\\":
                    if position >= len(raw):
                        break
                    char = raw[position]
                    position += 1
                chars.append(char)
            raise ValueError("Unterminated Autolith string")
        start = position
        while position < len(raw) and not raw[position].isspace() and raw[position] not in "()":
            position += 1
        token = raw[start:position]
        if re.fullmatch(r":[A-Za-z][A-Za-z0-9_-]*", token):
            return Keyword(token[1:].lower())
        if token.lower() == "nil":
            return None
        if token.lower() == "t":
            return True
        if re.fullmatch(r"[+-]?\d+", token):
            return int(token)
        if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eEdD][+-]?\d+)?", token):
            value = float(re.sub("[dD]", "e", token))
            if math.isfinite(value):
                return value
        raise ValueError(f"Unsupported Autolith data token: {token[:50]!r}")

    value = form()
    skip()
    if position != len(raw):
        raise ValueError("Autolith result contains extra top-level forms")
    return value


def plist(value: object, tag: str | None = None) -> dict:
    if not isinstance(value, list):
        raise ValueError("Expected an Autolith property list")
    if tag is not None:
        if not value or not isinstance(value[0], Keyword) or value[0] != tag:
            raise ValueError(f"Expected :{tag} data")
        value = value[1:]
    if len(value) % 2:
        raise ValueError("Autolith property list has an unmatched key")
    result = {}
    for index in range(0, len(value), 2):
        key = value[index]
        if not isinstance(key, Keyword) or key in result:
            raise ValueError("Autolith property list has a non-keyword or duplicate key")
        result[str(key)] = value[index + 1]
    return result


def json_from_sexp(value: object) -> object:
    if isinstance(value, Keyword):
        if value == "null":
            return None
        raise ValueError("Unexpected keyword in Autolith JSON data")
    if isinstance(value, list):
        if not value or not isinstance(value[0], Keyword):
            raise ValueError("Autolith JSON lists must have :object or :array tags")
        if value[0] == "array":
            return [json_from_sexp(item) for item in value[1:]]
        if value[0] == "object":
            result = {}
            for pair in value[1:]:
                if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str) or isinstance(pair[0], Keyword) or pair[0] in result:
                    raise ValueError("Invalid or duplicate Autolith JSON object member")
                result[pair[0]] = json_from_sexp(pair[1])
            return result
        raise ValueError("Unknown Autolith JSON container tag")
    if value is None:
        return False
    return value


def sexp_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def schema_sexp(schema: dict) -> str:
    """Project the native output shape; Python retains full acceptance checks."""
    kind = schema["type"]
    if kind not in {"object", "array", "string", "number", "integer", "boolean", "null"}:
        raise ValueError(f"Unsupported worker output type: {kind}")
    fields = [":type", f":{kind}"]
    if "properties" in schema:
        properties = " ".join(
            f"({sexp_string(key)} {schema_sexp(value)})"
            for key, value in schema["properties"].items()
        )
        fields.extend([":properties", f"({properties})"])
    if "required" in schema:
        fields.extend([":required", "(" + " ".join(map(sexp_string, schema["required"])) + ")"])
    if schema.get("additionalProperties") is False:
        fields.extend([":additional-properties", "nil"])
    if "items" in schema:
        fields.extend([":items", schema_sexp(schema["items"])])
    if "enum" in schema:
        if any(not isinstance(item, str) for item in schema["enum"]):
            raise ValueError("Native worker enums must contain strings")
        fields.extend([":enum", "(" + " ".join(map(sexp_string, schema["enum"])) + ")"])
    if "minItems" in schema:
        fields.extend([":min-items", str(schema["minItems"])])
    return "(" + " ".join(fields) + ")"


def autolith_result(raw: str, schema: dict | None) -> dict:
    fields = plist(read_sexp(raw), "autolith-job-result")
    status = fields.get("status")
    if type(fields.get("version")) is not int or fields["version"] != 1 or not isinstance(status, Keyword) or status != "succeeded":
        raise ValueError(f"Autolith job did not succeed: {fields.get('status')}")
    payload = json_from_sexp(fields.get("result"))
    if schema is not None:
        validate_schema(payload, schema)
    usage = plist(fields["usage"]) if fields.get("usage") is not None else {}
    for value in usage.values():
        if type(value) is not int or value < 0:
            raise ValueError("Autolith returned invalid usage counters")
    return {
        "type": "result",
        "is_error": False,
        "subtype": "success",
        "structured_output": payload,
        "result": payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
        "modelUsage": {},
        "usage": {
            "input_tokens": usage.get("input-tokens", 0),
            "output_tokens": usage.get("output-tokens", 0),
        },
        "provider_requests": usage.get("provider-requests"),
        "model_provenance": "unavailable_in_job_envelope",
        "trace_id": fields.get("trace-id"),
        "host": "autolith",
    }
