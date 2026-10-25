#!/usr/bin/env python3
"""Exercise the pinned DBHub configuration using a disposable SQLite database.

Requires Node.js >=22.5 and npx. The first run downloads the pinned package.
No database credentials or Claude authentication are needed.
"""

import json
import os
import selectors
import signal
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

PACKAGE = "@bytebase/dbhub@1.5.0"
CONFIG = Path(__file__).resolve().parents[1] / "references/dbhub.toml"


def receive(process: subprocess.Popen, request_id: int) -> dict:
    deadline = time.monotonic() + 120
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("DBHub exited before responding")
            response = json.loads(line)
            if response.get("id") == request_id:
                if "error" in response:
                    raise RuntimeError(str(response["error"]))
                return response["result"]
    raise TimeoutError("Timed out waiting for DBHub")


def send(process: subprocess.Popen, message: dict) -> None:
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def request(
    process: subprocess.Popen, request_id: int, method: str, params: dict
) -> dict:
    send(
        process,
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
    )
    return receive(process, request_id)


def check_tools(process: subprocess.Popen) -> None:
    initialized = request(
        process,
        1,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "workflow-db-smoke", "version": "1.0.0"},
        },
    )
    if "serverInfo" not in initialized:
        raise RuntimeError("Missing MCP server information")
    send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools = request(process, 2, "tools/list", {})["tools"]
    query_tool = next(
        tool["name"] for tool in tools if tool["name"].startswith("execute_sql")
    )
    result = request(
        process,
        3,
        "tools/call",
        {
            "name": query_tool,
            "arguments": {"sql": "SELECT 1 AS smoke_ok"},
        },
    )
    if result.get("isError") or "smoke_ok" not in json.dumps(result):
        raise RuntimeError(f"SELECT failed: {result}")
    rejected = request(
        process,
        4,
        "tools/call",
        {
            "name": query_tool,
            "arguments": {"sql": "CREATE TABLE forbidden (id INTEGER)"},
        },
    )
    if not rejected.get("isError"):
        raise RuntimeError(f"Read-only tool accepted a write: {rejected}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="workflow-db-smoke-") as directory:
        database = Path(directory) / "analytics.db"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE fixture (id INTEGER)")
        with tempfile.TemporaryFile(mode="w+") as diagnostics:
            process = subprocess.Popen(
                [
                    "npx",
                    "--yes",
                    PACKAGE,
                    "--transport",
                    "stdio",
                    "--config",
                    str(CONFIG),
                ],
                cwd=directory,
                env={**os.environ, "ANALYTICS_DATABASE_URL": f"sqlite://{database}"},
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=diagnostics,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            try:
                check_tools(process)
            except Exception:
                diagnostics.seek(0)
                print(diagnostics.read())
                raise
            finally:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
        with sqlite3.connect(database) as connection:
            if connection.execute(
                "SELECT name FROM sqlite_master WHERE name='forbidden'"
            ).fetchall():
                raise RuntimeError("Read-only check modified the database")
    print(
        f"PASS: {PACKAGE}: initialize, tools/list, SELECT, and write rejection (SQLite)"
    )


if __name__ == "__main__":
    main()
