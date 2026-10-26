#!/usr/bin/env python3
"""Resolve Jira/Linear tickets through CLI-first, explicitly configured APIs."""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROVIDERS = ("jira", "linear")
OPERATIONS = ("get", "statuses", "transition", "link-pr")
KEY = re.compile(r"[A-Z][A-Z0-9_]*-[1-9][0-9]*\Z")
CONFIG_PATH = ".claude/ticket-tracker.json"
MAX_RESPONSE = 5 * 1024 * 1024
ACLI = {
    "get": ["acli", "jira", "workitem", "view", "{key}", "--json", "--fields", "*all"],
    "transition": [
        "acli",
        "jira",
        "workitem",
        "transition",
        "--key",
        "{key}",
        "--status",
        "{status}",
        "--yes",
    ],
    "doctor": ["acli", "jira", "auth", "status"],
    "version": ["acli", "--version"],
}


class TicketError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def fail(code: str, message: str):
    raise TicketError(code, message)


def object_value(value, label):
    if not isinstance(value, dict):
        fail("invalid_response", f"{label} must be a JSON object")
    return value


def https_url(value, label, *, origin_only=False):
    if not isinstance(value, str):
        fail("invalid_config", f"{label} must be an HTTPS URL")
    try:
        parsed = urllib.parse.urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )
        if origin_only and parsed.path not in ("", "/"):
            valid = False
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        fail(
            "invalid_config",
            f"{label} must be an HTTPS URL without credentials, query, or fragment",
        )
    return value.rstrip("/")


def load_config(project: Path):
    try:
        config = json.loads((project / CONFIG_PATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, ValueError):
        fail("invalid_config", f"Cannot read valid JSON from {CONFIG_PATH}")
    if not isinstance(config, dict):
        fail("invalid_config", "Ticket configuration must be an object")
    if set(config) - {"version", "default_provider", "providers", "timeout"}:
        fail("invalid_config", "Unknown ticket configuration field")
    if type(config.get("version", 1)) is not int or config.get("version", 1) != 1:
        fail("invalid_config", "Only ticket configuration version 1 is supported")
    if config.get("default_provider") not in (*PROVIDERS, None):
        fail("invalid_config", "default_provider must be jira or linear")
    timeout = config.get("timeout", 30)
    if type(timeout) not in (int, float) or not 0 < timeout <= 120:
        fail(
            "invalid_config",
            "timeout must be greater than zero and at most 120 seconds",
        )
    providers = config.get("providers", {})
    if not isinstance(providers, dict) or set(providers) - set(PROVIDERS):
        fail("invalid_config", "providers must contain only jira and/or linear")
    for name, settings in providers.items():
        if not isinstance(settings, dict) or set(settings) - {
            "site",
            "workspace",
            "transport",
            "api",
            "cli",
            "status_map",
            "acceptance_fields",
        }:
            fail("invalid_config", f"Invalid {name} provider settings")
        if settings.get("transport", "auto") not in ("auto", "cli", "api"):
            fail("invalid_config", "transport must be auto, cli, or api")
        if "site" in settings:
            settings["site"] = https_url(settings["site"], "site", origin_only=True)
        if "workspace" in settings and (
            not isinstance(settings["workspace"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", settings["workspace"])
        ):
            fail("invalid_config", "workspace must be a Linear workspace URL slug")
        for field in ("status_map", "api", "cli"):
            if field in settings and not isinstance(settings[field], dict):
                fail("invalid_config", f"{field} must be an object")
        for value in settings.get("status_map", {}).values():
            if not isinstance(value, str) or not value.strip():
                fail(
                    "invalid_config",
                    "status_map values must be nonempty native status names or IDs",
                )
        fields = settings.get("acceptance_fields", [])
        if not isinstance(fields, list) or not all(
            isinstance(f, str) and f for f in fields
        ):
            fail("invalid_config", "acceptance_fields must be a list of field IDs")
        api = settings.get("api", {})
        if set(api) - {"token_env", "email_env", "auth", "base_url"}:
            fail("invalid_config", "Unknown API configuration field")
        for field in ("token_env", "email_env"):
            if field in api and (
                not isinstance(api[field], str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api[field])
            ):
                fail("invalid_config", f"{field} must name an environment variable")
        if api.get("auth", "basic" if name == "jira" else "token") not in (
            ("basic", "bearer") if name == "jira" else ("token", "bearer")
        ):
            fail("invalid_config", f"Unsupported {name} API authentication mode")
        if "base_url" in api:
            api["base_url"] = https_url(api["base_url"], "api.base_url")
            if name == "linear" and api["base_url"] != "https://api.linear.app/graphql":
                fail(
                    "invalid_config",
                    "Linear API requests use https://api.linear.app/graphql",
                )
        cli = settings.get("cli", {})
        if set(cli) - {*OPERATIONS, "doctor", "version"}:
            fail("invalid_config", "Unknown CLI operation")
        allowed = {"{key}", "{id}", "{url}", "{status}", "{site}", "{workspace}"}
        for operation, argv in cli.items():
            if (
                not isinstance(argv, list)
                or not argv
                or not all(isinstance(a, str) and a for a in argv)
            ):
                fail(
                    "invalid_config", "CLI operations must be nonempty argument arrays"
                )
            if "{" in argv[0] or "}" in argv[0]:
                fail("invalid_config", "CLI executable cannot be a placeholder")
            for arg in argv[1:]:
                if ("{" in arg or "}" in arg) and arg not in allowed:
                    fail(
                        "invalid_config",
                        "CLI placeholders must occupy a whole argument",
                    )
            if operation in ("version", "doctor") and any(a in allowed for a in argv):
                fail(
                    "invalid_config",
                    "version and doctor commands cannot require ticket placeholders",
                )
    return config


def parse_reference(value, config, explicit=None):
    provider = None
    scope = None
    if "://" in value:
        value = https_url(value, "ticket reference")
        parsed = urllib.parse.urlsplit(value)
        linear = re.fullmatch(r"/([^/]+)/issue/([^/]+)(?:/.*)?", parsed.path)
        jira = re.fullmatch(r"/browse/([^/]+)/?", parsed.path)
        if parsed.hostname == "linear.app" and linear:
            provider, scope, value = "linear", linear[1], linear[2]
        elif jira:
            site = f"https://{parsed.netloc}"
            configured = config.get("providers", {}).get("jira", {}).get("site")
            if not parsed.hostname.endswith(".atlassian.net") and site != configured:
                fail(
                    "invalid_reference",
                    "Custom Jira URL hosts must match the configured site",
                )
            provider, scope, value = "jira", site, jira[1]
        else:
            fail("invalid_reference", "Expected a Jira browse URL or Linear issue URL")
    key = value.upper()
    if not KEY.fullmatch(key):
        fail(
            "invalid_reference", "Expected a ticket key such as ABC-123 or a ticket URL"
        )
    if explicit and provider and explicit != provider:
        fail("identity_mismatch", "Explicit tracker conflicts with the ticket URL")
    provider = explicit or provider or config.get("default_provider")
    return {"provider": provider, "scope": scope, "key": key}


def rich_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(rich_text(item) for item in value)
    if not isinstance(value, dict):
        return str(value)
    if value.get("type") == "hardBreak":
        return "\n"
    text = value.get("text", "")
    if not text and value.get("type") in ("mention", "inlineCard"):
        text = value.get("attrs", {}).get("text") or value.get("attrs", {}).get(
            "url", ""
        )
    text += "".join(rich_text(child) for child in value.get("content", []))
    if value.get("type") in ("paragraph", "heading", "listItem", "codeBlock"):
        text += "\n"
    return text


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, headers, timeout, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            **headers,
        },
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(
            request, timeout=timeout
        ) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as error:
        code = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            429: "rate_limited",
        }.get(error.code, "api_error")
        fail(
            code,
            f"Tracker API returned HTTP {error.code}; check the selected account/site and permissions",
        )
    except (urllib.error.URLError, TimeoutError, OSError):
        fail("connection_failed", "Tracker API connection failed or timed out")
    if len(raw) > MAX_RESPONSE:
        fail("invalid_response", "Tracker response exceeded 5 MiB")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        fail("invalid_response", "Tracker did not return valid JSON")


class Tickets:
    def __init__(self, project: Path, config=None):
        self.project = project.resolve()
        self.config = load_config(self.project) if config is None else config
        self.timeout = self.config.get("timeout", 30)

    def settings(self, provider):
        return self.config.get("providers", {}).get(provider, {})

    def cli(self, provider, operation):
        settings = self.settings(provider)
        return settings.get("cli", ACLI if provider == "jira" else {}).get(operation)

    def cli_available(self, provider, operation):
        argv = self.cli(provider, operation)
        return bool(argv and shutil.which(argv[0]))

    def api_credentials(self, provider):
        settings = self.settings(provider)
        api = settings.get("api", {})
        token = os.environ.get(
            api.get(
                "token_env",
                "JIRA_API_TOKEN" if provider == "jira" else "LINEAR_API_KEY",
            )
        )
        if not token:
            return None
        if provider == "linear":
            prefix = "Bearer " if api.get("auth", "token") == "bearer" else ""
            return "https://api.linear.app/graphql", {"Authorization": prefix + token}
        if not settings.get("site"):
            return None
        base = api.get("base_url", settings["site"] + "/rest/api/3")
        if api.get("auth", "basic") == "bearer":
            return base, {"Authorization": "Bearer " + token}
        email = os.environ.get(api.get("email_env", "JIRA_EMAIL"))
        if not email:
            return None
        credential = base64.b64encode(f"{email}:{token}".encode()).decode()
        return base, {"Authorization": "Basic " + credential}

    def transport(self, provider, operation):
        mode = self.settings(provider).get("transport", "auto")
        if mode != "api" and self.cli_available(provider, operation):
            return "cli"
        if mode != "cli" and self.api_credentials(provider):
            return "api"
        fail(
            "unavailable",
            f"No usable {provider} connection for {operation}; run tickets.py doctor and check {CONFIG_PATH}",
        )

    def resolve(self, value, explicit=None):
        ref = parse_reference(value, self.config, explicit)
        if ref["provider"] is None:
            candidates = []
            for provider in PROVIDERS:
                try:
                    self.transport(provider, "get")
                except TicketError:
                    continue
                candidates.append(provider)
            if len(candidates) != 1:
                fail(
                    "ambiguous_provider" if candidates else "unavailable",
                    "Choose --tracker jira|linear, use a ticket URL, or configure default_provider",
                )
            ref["provider"] = candidates[0]
        settings = self.settings(ref["provider"])
        expected = settings.get("site" if ref["provider"] == "jira" else "workspace")
        if ref["scope"] and expected and ref["scope"] != expected:
            fail(
                "identity_mismatch",
                "Ticket URL conflicts with the configured site/workspace",
            )
        ref["scope"] = ref["scope"] or expected
        return ref

    def run_cli(self, provider, operation, **values):
        template = self.cli(provider, operation)
        if not template or not self.cli_available(provider, operation):
            fail("unavailable", f"No installed CLI for {provider} {operation}")
        argv = []
        for arg in template:
            if arg.startswith("{") and arg.endswith("}"):
                value = values.get(arg[1:-1])
                if value is None:
                    fail("invalid_config", f"Missing value for CLI placeholder {arg}")
                argv.append(str(value))
            else:
                argv.append(arg)
        try:
            result = subprocess.run(
                argv,
                cwd=self.project,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError:
            fail("unavailable", "Configured CLI executable is unavailable")
        except (OSError, subprocess.TimeoutExpired):
            fail(
                "connection_failed",
                "Tracker CLI could not run or timed out; verify the operation before retrying writes",
            )
        if result.returncode:
            # CLI stderr can contain credentials; do not echo it into agent logs.
            fail(
                "cli_failed",
                f"{provider} CLI {operation} failed (exit {result.returncode}); check CLI authentication and permissions",
            )
        if operation == "version":
            version = (
                result.stdout.strip().splitlines()[0]
                if result.stdout.strip()
                else "unknown"
            )
            token_env = (
                self.settings(provider)
                .get("api", {})
                .get(
                    "token_env",
                    "JIRA_API_TOKEN" if provider == "jira" else "LINEAR_API_KEY",
                )
            )
            token = os.environ.get(token_env)
            return (version.replace(token, "[redacted]") if token else version)[:160]
        if operation in ("doctor", "transition", "link-pr"):
            return None
        try:
            return json.loads(result.stdout)
        except ValueError:
            fail(
                "invalid_response",
                f"{provider} CLI {operation} did not return valid JSON",
            )

    def api(self, provider, path="", payload=None):
        credentials = self.api_credentials(provider)
        if not credentials:
            fail(
                "unavailable",
                f"Configure {provider} API credentials separately from CLI authentication",
            )
        base, headers = credentials
        response = request_json(base + path, headers, self.timeout, payload)
        if provider == "linear":
            response = object_value(response, "GraphQL response")
            if response.get("errors"):
                fail(
                    "api_error",
                    "Linear GraphQL returned errors; no partial response is treated as success",
                )
            return object_value(response.get("data"), "GraphQL data")
        return response

    def graphql(self, query, variables=None):
        return self.api(
            "linear", payload={"query": query, "variables": variables or {}}
        )

    def normalize(self, ref, raw, transport):
        raw = object_value(raw, "Ticket")
        provider = ref["provider"]
        custom = transport == "cli" and "cli" in self.settings(provider)
        limits = []
        if custom:
            ticket = dict(raw)
            for field in ("id", "key", "url", "title", "status"):
                if not ticket.get(field):
                    fail(
                        "invalid_response",
                        f"Configured CLI get must return normalized ticket field {field}",
                    )
            ticket.setdefault("description", "")
            ticket.setdefault("comments", [])
            ticket.setdefault("links", [])
            ticket.setdefault("acceptance_criteria", [])
        elif provider == "jira":
            fields = object_value(raw.get("fields"), "Jira fields")
            self_url = raw.get("self")
            if not isinstance(self_url, str):
                fail(
                    "invalid_response",
                    "Jira response needs its self URL to verify the active site",
                )
            parsed = urllib.parse.urlsplit(https_url(self_url, "Jira response URL"))
            site = f"https://{parsed.netloc}"
            api_base = self.settings(provider).get("api", {}).get("base_url")
            if api_base and self_url == api_base + "/issue/" + str(raw.get("id")):
                # Scoped-token responses can identify the configured cloud ID
                # through the API gateway rather than the browser site's host.
                site = self.settings(provider).get("site") or site
            comments = fields.get("comment") or {}
            nodes = comments.get("comments", [])
            if comments.get("total", len(nodes)) > len(nodes) or len(nodes) > 50:
                limits.append("comments_truncated")
            links = []
            parent = fields.get("parent")
            if parent:
                links.append(
                    {
                        "type": "parent",
                        "key": parent.get("key"),
                        "url": site + "/browse/" + parent["key"],
                    }
                )
            for link in fields.get("issuelinks", []):
                linked = link.get("outwardIssue") or link.get("inwardIssue")
                if linked:
                    links.append(
                        {
                            "type": link.get("type", {}).get("name", "related"),
                            "key": linked["key"],
                            "url": site + "/browse/" + linked["key"],
                        }
                    )
            ticket = {
                "id": raw.get("id"),
                "key": raw.get("key"),
                "title": fields.get("summary"),
                "url": site + "/browse/" + str(raw.get("key")),
                "description": rich_text(fields.get("description")).strip(),
                "status": fields.get("status"),
                "assignee": fields.get("assignee"),
                "updated_at": fields.get("updated"),
                "links": links,
                "comments": [
                    {
                        "id": c.get("id"),
                        "body": rich_text(c.get("body")).strip(),
                        "author": (c.get("author") or {}).get("displayName"),
                    }
                    for c in nodes[:50]
                ],
                "acceptance_criteria": [
                    rich_text(fields[f]).strip()
                    for f in self.settings(provider).get("acceptance_fields", [])
                    if fields.get(f)
                ],
            }
        else:
            comments = raw.get("comments") or {}
            if comments.get("pageInfo", {}).get("hasNextPage"):
                limits.append("comments_truncated")
            ticket = {
                "id": raw.get("id"),
                "key": raw.get("identifier"),
                "url": raw.get("url"),
                "title": raw.get("title"),
                "description": raw.get("description") or "",
                "status": raw.get("state"),
                "assignee": raw.get("assignee"),
                "team_id": (raw.get("team") or {}).get("id"),
                "updated_at": raw.get("updatedAt"),
                "comments": [
                    {
                        "id": c.get("id"),
                        "body": c.get("body", ""),
                        "author": (c.get("user") or {}).get("name"),
                    }
                    for c in comments.get("nodes", [])
                ],
                "links": [
                    {
                        "type": "parent",
                        "key": raw["parent"]["identifier"],
                        "url": raw["parent"]["url"],
                    }
                ]
                if raw.get("parent")
                else [],
                "acceptance_criteria": [],
            }
        if (
            not isinstance(ticket.get("id"), (str, int))
            or not ticket.get("id")
            or not isinstance(ticket.get("title"), str)
        ):
            fail(
                "invalid_response", "Ticket response is missing its native ID or title"
            )
        if (
            ticket.get("provider", provider) != provider
            or ticket.get("key") != ref["key"]
        ):
            fail(
                "identity_mismatch",
                "Returned ticket does not match the requested provider/key",
            )
        actual = parse_reference(ticket.get("url", ""), self.config, provider)
        if actual["key"] != ref["key"] or (
            ref["scope"] and actual["scope"] != ref["scope"]
        ):
            fail(
                "identity_mismatch",
                "Returned ticket belongs to a different site/workspace",
            )
        status = object_value(ticket.get("status"), "Ticket status")
        if not status.get("id") or not isinstance(status.get("name"), str):
            fail("invalid_response", "Ticket status needs its native ID and name")
        if not isinstance(ticket.get("description"), str):
            fail("invalid_response", "Ticket description must be text")
        for field in ("comments", "links", "acceptance_criteria", "limitations"):
            if not isinstance(ticket.get(field, []), list):
                fail("invalid_response", f"Ticket {field} must be a list")
        ticket.update(
            schema_version=1,
            provider=provider,
            id=str(ticket["id"]),
            scope=actual["scope"],
            transport=transport,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        ticket["limitations"] = list(
            dict.fromkeys(ticket.get("limitations", []) + limits)
        )
        return ticket

    def get(self, ref, transport=None):
        provider = ref["provider"]
        transport = transport or self.transport(provider, "get")
        if transport == "cli":
            raw = self.run_cli(
                provider,
                "get",
                key=ref["key"],
                site=ref["scope"],
                workspace=ref["scope"],
            )
        elif provider == "jira":
            raw = self.api(
                provider,
                "/issue/" + urllib.parse.quote(ref["key"], safe="") + "?fields=*all",
            )
        else:
            raw = self.graphql(
                """query Ticket($id: String!) { issue(id: $id) {
                id identifier url title description updatedAt state { id name type }
                assignee { id name } team { id } parent { identifier url }
                comments(first: 50) { nodes { id body user { name } } pageInfo { hasNextPage } }
            } }""",
                {"id": ref["key"]},
            ).get("issue")
            if raw is None:
                fail(
                    "not_found", "Linear ticket was not found in the selected workspace"
                )
        return self.normalize(ref, raw, transport)

    def bound(self, ticket):
        return {
            "provider": ticket["provider"],
            "key": ticket["key"],
            "scope": ticket["scope"],
        }

    def cli_values(self, ticket, **overrides):
        return {
            "key": ticket["key"],
            "id": ticket["id"],
            "url": ticket["url"],
            "site": ticket["scope"],
            "workspace": ticket["scope"],
            **overrides,
        }

    def check_transport_identity(self, ticket, transport):
        if transport != ticket["transport"]:
            confirmed = self.get(self.bound(ticket), transport)
            if confirmed["id"] != ticket["id"]:
                fail(
                    "identity_mismatch",
                    "CLI and API returned different native ticket IDs",
                )
            return confirmed
        return ticket

    def statuses(self, ticket, transport=None):
        provider = ticket["provider"]
        transport = transport or self.transport(provider, "statuses")
        ticket = self.check_transport_identity(ticket, transport)
        if transport == "cli":
            states = self.run_cli(provider, "statuses", **self.cli_values(ticket))
        elif provider == "jira":
            data = object_value(
                self.api(
                    provider,
                    f"/issue/{urllib.parse.quote(ticket['id'], safe='')}/transitions",
                ),
                "Jira transitions",
            )
            states = [
                {"id": s["id"], "name": s["to"]["name"], "status_id": s["to"]["id"]}
                for s in data.get("transitions", [])
            ]
        else:
            if not ticket.get("team_id"):
                # A normalized CLI adapter need not include API-specific team metadata.
                ticket = self.get(self.bound(ticket), "api")
            data = self.graphql(
                """query TicketStates($id: String!) { team(id: $id) {
                states(first: 100) { nodes { id name type } pageInfo { hasNextPage } }
            } }""",
                {"id": ticket["team_id"]},
            )
            connection = object_value(
                (data.get("team") or {}).get("states"), "Linear workflow states"
            )
            if connection.get("pageInfo", {}).get("hasNextPage"):
                fail(
                    "incomplete_response",
                    "Workflow state response is truncated; choose a CLI adapter with full state discovery",
                )
            states = connection.get("nodes")
        if not isinstance(states, list) or any(
            not isinstance(s, dict)
            or not s.get("id")
            or not isinstance(s.get("name"), str)
            for s in states
        ):
            fail(
                "invalid_response",
                "statuses must return a JSON list with native id and name fields",
            )
        return states

    def transition(self, ticket, requested, apply=False):
        provider = ticket["provider"]
        target = self.settings(provider).get("status_map", {}).get(requested, requested)
        current = ticket["status"]
        result = {
            "operation": "transition",
            "ticket": self.bound(ticket),
            "id": ticket["id"],
            "target": target,
        }
        if target in (str(current["id"]), current["name"]):
            return {**result, "status": "unchanged"}
        transport = self.transport(provider, "transition")
        ticket = self.check_transport_identity(ticket, transport)
        builtin_acli = transport == "cli" and "cli" not in self.settings(provider)
        if builtin_acli:
            if target.isdigit():
                fail(
                    "unsupported",
                    "ACLI transitions need a native status name; use API for native status IDs",
                )
            state = {"id": None, "name": target}
        else:
            # API writes need their own reachable action IDs. A custom CLI
            # may discover states through its separately configured API.
            states = self.statuses(ticket, "api" if transport == "api" else None)
            matches = [
                s
                for s in states
                if target == str(s.get("status_id", s["id"]))
                or target.casefold() == s["name"].casefold()
            ]
            if len(matches) != 1:
                fail(
                    "ambiguous_status" if matches else "invalid_status",
                    "Choose one reachable native status name or status ID from statuses",
                )
            state = matches[0]
        result.update(
            transport=transport, target=state["name"], native_action_id=state["id"]
        )
        if not apply:
            return {**result, "status": "planned"}
        try:
            if transport == "cli":
                self.run_cli(
                    provider,
                    "transition",
                    **self.cli_values(
                        ticket,
                        status=state.get("status_id", state["id"]) or state["name"],
                    ),
                )
            elif provider == "jira":
                self.api(
                    provider,
                    f"/issue/{urllib.parse.quote(ticket['id'], safe='')}/transitions",
                    {"transition": {"id": state["id"]}},
                )
            else:
                data = self.graphql(
                    "mutation MoveTicket($id: String!, $state: String!) { issueUpdate(id: $id, input: {stateId: $state}) { success } }",
                    {"id": ticket["id"], "state": state["id"]},
                )
                if not (data.get("issueUpdate") or {}).get("success"):
                    fail("api_error", "Linear did not confirm the transition")
            verified = self.get(self.bound(ticket), transport)
            expected_status_id = state.get("status_id", state["id"])
            if (
                verified["id"] != ticket["id"]
                or verified["status"]["name"] != state["name"]
                or (
                    expected_status_id is not None
                    and str(verified["status"]["id"]) != str(expected_status_id)
                )
            ):
                fail(
                    "verification_failed",
                    "Ticket status did not match the requested result",
                )
        except TicketError as error:
            fail(
                "write_unconfirmed",
                f"Transition outcome is unconfirmed ({error.code}); re-read the ticket before retrying",
            )
        return {**result, "status": "applied", "verified_status": verified["status"]}

    def link_pr(self, ticket, url, apply=False):
        url = https_url(url, "pull request URL")
        if not re.search(
            r"/(pull|pulls|merge_requests)/[1-9][0-9]*/?$",
            urllib.parse.urlsplit(url).path,
        ):
            fail(
                "invalid_reference",
                "Expected a pull/merge request URL ending in its number",
            )
        provider = ticket["provider"]
        transport = self.transport(provider, "link-pr")
        self.check_transport_identity(ticket, transport)
        result = {
            "operation": "link-pr",
            "ticket": self.bound(ticket),
            "id": ticket["id"],
            "url": url,
            "transport": transport,
        }
        if not apply:
            return {**result, "status": "planned"}
        try:
            if transport == "cli":
                self.run_cli(provider, "link-pr", **self.cli_values(ticket, url=url))
            elif provider == "jira":
                response = self.api(
                    provider,
                    f"/issue/{urllib.parse.quote(ticket['id'], safe='')}/remotelink",
                    {
                        "globalId": "agentic-coding-workflow:pr:"
                        + hashlib.sha256(url.encode()).hexdigest(),
                        "object": {"url": url, "title": "Pull request"},
                    },
                )
                if not object_value(response, "Jira remote link").get("id"):
                    fail("invalid_response", "Jira did not confirm the PR link ID")
            else:
                data = self.graphql(
                    """mutation LinkPullRequest($issue: String!, $url: String!) {
                    attachmentCreate(input: {issueId: $issue, url: $url, title: "Pull request"}) {
                        success attachment { id url }
                    } }""",
                    {"issue": ticket["id"], "url": url},
                )
                attachment = data.get("attachmentCreate") or {}
                if (
                    not attachment.get("success")
                    or not (attachment.get("attachment") or {}).get("id")
                    or (attachment.get("attachment") or {}).get("url") != url
                ):
                    fail("api_error", "Linear did not confirm the PR link")
        except TicketError as error:
            fail(
                "write_unconfirmed",
                f"PR link outcome is unconfirmed ({error.code}); inspect the ticket before retrying",
            )
        return {**result, "status": "applied"}

    def doctor(self, check=False):
        reports = []
        for provider in PROVIDERS:
            mode = self.settings(provider).get("transport", "auto")
            capabilities = [
                operation
                for operation in OPERATIONS
                if self.cli_available(provider, operation)
            ]
            cli = {
                "available": bool(capabilities),
                "capabilities": capabilities,
                "version": "not_checked",
                "authentication": "not_checked",
            }
            if capabilities and self.cli_available(provider, "version"):
                try:
                    cli["version"] = self.run_cli(provider, "version")
                except TicketError as error:
                    cli["version"] = error.code
            if check and capabilities and self.cli_available(provider, "doctor"):
                try:
                    self.run_cli(provider, "doctor")
                    cli["authentication"] = "authenticated"
                except TicketError as error:
                    cli["authentication"] = error.code
            api = {
                "configured": bool(self.api_credentials(provider)),
                "authentication": "not_checked",
                "write_permissions": "not_checked",
            }
            if check and api["configured"]:
                try:
                    if provider == "jira":
                        identity = self.api(provider, "/myself")
                        if not object_value(identity, "Jira identity").get("accountId"):
                            fail(
                                "invalid_response",
                                "Jira identity did not contain accountId",
                            )
                    else:
                        identity = self.graphql(
                            "query TicketIdentity { viewer { id } }"
                        )
                        if not (identity.get("viewer") or {}).get("id"):
                            fail(
                                "invalid_response",
                                "Linear identity did not contain viewer.id",
                            )
                    api["authentication"] = "authenticated"
                except TicketError as error:
                    api["authentication"] = error.code
            reports.append(
                {"provider": provider, "transport": mode, "cli": cli, "api": api}
            )
        return {"status": "inspected", "config": CONFIG_PATH, "providers": reports}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--tracker", choices=PROVIDERS)
    subcommands = parser.add_subparsers(dest="operation", required=True)
    doctor = subcommands.add_parser(
        "doctor", help="Inspect installed connections without changing authentication"
    )
    doctor.add_argument(
        "--check",
        action="store_true",
        help="Also perform read-only authentication probes",
    )
    for operation in OPERATIONS:
        command = subcommands.add_parser(operation)
        command.add_argument("reference")
        if operation == "transition":
            command.add_argument(
                "status", help="Configured semantic status or exact native status"
            )
        if operation == "link-pr":
            command.add_argument("url")
        if operation in ("transition", "link-pr"):
            command.add_argument(
                "--apply",
                action="store_true",
                help="Execute the external write; otherwise only prepare it",
            )
    args = parser.parse_args(argv)
    try:
        tickets = Tickets(args.project_dir)
        if args.operation == "doctor":
            report = tickets.doctor(args.check)
        else:
            ref = tickets.resolve(args.reference, args.tracker)
            ticket = tickets.get(ref)
            if args.operation == "get":
                report = ticket
            elif args.operation == "statuses":
                report = {
                    "ticket": tickets.bound(ticket),
                    "statuses": tickets.statuses(ticket),
                }
            elif args.operation == "transition":
                report = tickets.transition(ticket, args.status, args.apply)
            else:
                report = tickets.link_pr(ticket, args.url, args.apply)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except TicketError as error:
        print(json.dumps({"status": "error", "code": error.code, "error": str(error)}))
        return 2
    except (KeyError, TypeError, ValueError, AttributeError):
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": "invalid_response",
                    "error": "Tracker returned malformed data; check the configured adapter contract",
                }
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
