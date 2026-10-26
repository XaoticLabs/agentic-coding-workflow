"""Exercise provider identity, CLI/API boundaries, and ticket write outcomes."""

import copy
import importlib.util
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/tickets.py"
SPEC = importlib.util.spec_from_file_location("workflow_tickets", SCRIPT)
tickets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tickets)


@pytest.fixture(autouse=True)
def no_external_connections(monkeypatch):
    for name in ("JIRA_EMAIL", "JIRA_API_TOKEN", "LINEAR_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(tickets.shutil, "which", lambda _: None)

    def unexpected_network(*args, **kwargs):
        pytest.fail("Unexpected live network request")

    monkeypatch.setattr(tickets.urllib.request, "build_opener", unexpected_network)


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "project with spaces"
    (path / ".claude").mkdir(parents=True)
    return path


def client(project, config=None):
    (project / tickets.CONFIG_PATH).write_text(json.dumps(config or {}))
    return tickets.Tickets(project)


def jira_issue(
    *,
    site="https://example.atlassian.net",
    key="ABC-123",
    status="To Do",
    status_id="1",
    native_id="10001",
):
    return {
        "id": native_id,
        "key": key,
        "self": site + "/rest/api/3/issue/" + native_id,
        "fields": {
            "summary": "Preserve cancelled requests",
            "description": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Keep the original deadline."}
                        ],
                    }
                ],
            },
            "status": {"id": status_id, "name": status},
            "assignee": None,
            "comment": {
                "total": 2,
                "comments": [{"id": "c1", "body": "Retain retry behavior"}],
            },
            "customfield_123": "Cancellation must propagate",
        },
    }


def linear_issue(*, workspace="acme", key="ABC-123", status="Todo", status_id="todo"):
    return {
        "id": "linear-id",
        "identifier": key,
        "url": f"https://linear.app/{workspace}/issue/{key}/cancel",
        "title": "Preserve cancelled requests",
        "description": "Keep **deadlines**.",
        "state": {"id": status_id, "name": status},
        "team": {"id": "team-id"},
        "parent": {
            "identifier": "ABC-100",
            "url": f"https://linear.app/{workspace}/issue/ABC-100/parent",
        },
        "comments": {
            "nodes": [{"id": "c1", "body": "Keep retries", "user": None}],
            "pageInfo": {"hasNextPage": True},
        },
    }


def jira_api_client(project, monkeypatch, **settings):
    monkeypatch.setenv("JIRA_EMAIL", "engineer@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "private-jira-token")
    return client(
        project,
        {
            "default_provider": "jira",
            "providers": {
                "jira": {"site": "https://example.atlassian.net", **settings}
            },
        },
    )


def linear_api_client(project, monkeypatch, **settings):
    monkeypatch.setenv("LINEAR_API_KEY", "private-linear-token")
    return client(
        project,
        {
            "default_provider": "linear",
            "providers": {"linear": {"workspace": "acme", **settings}},
        },
    )


def serve(monkeypatch, handler):
    calls = []

    def request(url, headers, timeout, payload=None):
        calls.append((url, headers, payload))
        return handler(url, payload)

    monkeypatch.setattr(tickets, "request_json", request)
    return calls


@pytest.mark.parametrize(
    "config",
    [
        [],
        {"default_provider": "github"},
        {"version": True},
        {"version": 2},
        {"providers": []},
        {"timeout": True},
        {"timeout": 0},
        {"timeout": 121},
        {"providers": {"jira": {"transport": "mcp"}}},
        {"providers": {"jira": {"site": "http://example.atlassian.net"}}},
        {"providers": {"jira": {"site": "https://token@example.atlassian.net"}}},
        {"providers": {"linear": {"api": {"token": "do-not-store-this"}}}},
        {
            "providers": {
                "linear": {"api": {"base_url": "https://other.example/graphql"}}
            }
        },
        {"providers": {"linear": {"cli": {"get": "linear view {key}"}}}},
        {"providers": {"linear": {"cli": {"get": ["linear", "--id={key}"]}}}},
        {"providers": {"linear": {"cli": {"get": ["{key}"]}}}},
        {"providers": {"linear": {"cli": {"doctor": ["linear", "{key}"]}}}},
        {"providers": {"jira": {"status_map": {"done": 3}}}},
    ],
)
def test_rejects_invalid_configuration(project, config):
    (project / tickets.CONFIG_PATH).write_text(json.dumps(config))
    with pytest.raises(tickets.TicketError) as error:
        tickets.Tickets(project)
    assert error.value.code == "invalid_config"
    assert "do-not-store-this" not in str(error.value)


def test_urls_select_provider_but_conflicts_never_switch_accounts(project):
    api = client(project, {"default_provider": "jira"})
    ref = api.resolve("https://linear.app/acme/issue/ABC-123/title")
    assert ref == {"provider": "linear", "scope": "acme", "key": "ABC-123"}
    with pytest.raises(tickets.TicketError, match="conflicts"):
        api.resolve("https://linear.app/acme/issue/ABC-123/title", "jira")


@pytest.mark.parametrize(
    "ref",
    [
        "ABC-0",
        "ABC-123;touch x",
        "https://evil.example/browse/ABC-123",
        "https://linear.app/acme/issue/ABC-123?token=x",
    ],
)
def test_rejects_invalid_or_unconfigured_references(project, ref):
    with pytest.raises(tickets.TicketError):
        client(project).resolve(ref)


def test_ambiguous_key_requires_selection_instead_of_querying_both(
    project, monkeypatch
):
    monkeypatch.setattr(tickets.shutil, "which", lambda _: "/bin/acli")
    monkeypatch.setenv("LINEAR_API_KEY", "private-linear-token")
    api = client(project)
    with pytest.raises(tickets.TicketError) as error:
        api.resolve("ABC-123")
    assert error.value.code == "ambiguous_provider"
    assert api.resolve("ABC-123", "jira")["provider"] == "jira"


def test_single_available_provider_is_selected_without_installing_tools(
    project, monkeypatch
):
    monkeypatch.setenv("LINEAR_API_KEY", "private-linear-token")
    assert client(project).resolve("abc-123")["provider"] == "linear"


def test_jira_api_normalizes_adf_and_reports_incomplete_context(project, monkeypatch):
    api = jira_api_client(project, monkeypatch, acceptance_fields=["customfield_123"])
    calls = serve(monkeypatch, lambda url, payload: jira_issue())
    ticket = api.get(api.resolve("ABC-123"))
    assert ticket["description"] == "Keep the original deadline."
    assert ticket["acceptance_criteria"] == ["Cancellation must propagate"]
    assert ticket["limitations"] == ["comments_truncated"]
    assert ticket["scope"] == "https://example.atlassian.net"
    assert ticket["transport"] == "api"
    assert (
        calls[0][0]
        == "https://example.atlassian.net/rest/api/3/issue/ABC-123?fields=*all"
    )
    assert calls[0][1]["Authorization"].startswith("Basic ")
    assert "private-jira-token" not in json.dumps(ticket)


def test_api_does_not_send_jira_credentials_to_a_site_taken_only_from_input(
    project, monkeypatch
):
    monkeypatch.setenv("JIRA_EMAIL", "engineer@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "private-jira-token")
    api = client(project)
    with pytest.raises(tickets.TicketError) as error:
        api.get(api.resolve("https://unconfigured.atlassian.net/browse/ABC-123"))
    assert error.value.code == "unavailable"


@pytest.mark.parametrize(
    "site", ["https://wrong.atlassian.net", "https://example.atlassian.net"]
)
def test_acli_read_preserves_site_identity(project, monkeypatch, site):
    api = client(
        project,
        {
            "default_provider": "jira",
            "providers": {"jira": {"site": "https://example.atlassian.net"}},
        },
    )
    monkeypatch.setattr(tickets.shutil, "which", lambda _: "/bin/acli")
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs["cwd"] == project.resolve()
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(
            argv, 0, json.dumps(jira_issue(site=site)), ""
        )

    monkeypatch.setattr(tickets.subprocess, "run", run)
    if site != "https://example.atlassian.net":
        with pytest.raises(tickets.TicketError) as error:
            api.get(api.resolve("ABC-123"))
        assert error.value.code == "identity_mismatch"
    else:
        assert api.get(api.resolve("ABC-123"))["transport"] == "cli"
    assert calls == [
        ["acli", "jira", "workitem", "view", "ABC-123", "--json", "--fields", "*all"]
    ]


def test_cli_failure_does_not_fall_back_to_api_and_does_not_leak_stderr(
    project, monkeypatch, capsys
):
    jira_api_client(project, monkeypatch)
    monkeypatch.setattr(tickets.shutil, "which", lambda _: "/bin/acli")
    monkeypatch.setattr(
        tickets.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 1, "", "Authorization: private-jira-token"
        ),
    )
    assert tickets.main(["--project-dir", str(project), "get", "ABC-123"]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["code"] == "cli_failed"
    assert "private-jira-token" not in output


def test_missing_cli_operation_uses_api_and_checks_native_identity(
    project, monkeypatch
):
    api = jira_api_client(project, monkeypatch)
    monkeypatch.setattr(tickets.shutil, "which", lambda _: "/bin/acli")
    monkeypatch.setattr(api, "run_cli", lambda *args, **kwargs: jira_issue())
    ticket = api.get(api.resolve("ABC-123"))
    calls = serve(
        monkeypatch,
        lambda url, payload: (
            jira_issue()
            if "/issue/ABC-123?" in url
            else {
                "transitions": [{"id": "31", "to": {"id": "3", "name": "In Progress"}}]
            }
        ),
    )
    assert api.statuses(ticket) == [
        {"id": "31", "status_id": "3", "name": "In Progress"}
    ]
    assert len(calls) == 2
    serve(monkeypatch, lambda url, payload: jira_issue(native_id="different"))
    with pytest.raises(tickets.TicketError) as error:
        api.statuses(ticket)
    assert error.value.code == "identity_mismatch"


def test_explicit_cli_mode_does_not_use_configured_api_for_missing_operation(
    project, monkeypatch
):
    api = jira_api_client(project, monkeypatch, transport="cli")
    with pytest.raises(tickets.TicketError) as error:
        api.transport("jira", "link-pr")
    assert error.value.code == "unavailable"


def test_linear_api_preserves_markdown_and_checks_workspace(project, monkeypatch):
    api = linear_api_client(project, monkeypatch)
    calls = serve(monkeypatch, lambda url, payload: {"data": {"issue": linear_issue()}})
    ticket = api.get(api.resolve("ABC-123"))
    assert ticket["description"] == "Keep **deadlines**."
    assert ticket["team_id"] == "team-id"
    assert ticket["links"][0]["key"] == "ABC-100"
    assert ticket["limitations"] == ["comments_truncated"]
    assert calls[0][1]["Authorization"] == "private-linear-token"
    assert calls[0][2]["variables"] == {"id": "ABC-123"}
    serve(
        monkeypatch,
        lambda url, payload: {"data": {"issue": linear_issue(workspace="other")}},
    )
    with pytest.raises(tickets.TicketError) as error:
        api.get(api.resolve("ABC-123"))
    assert error.value.code == "identity_mismatch"


def test_graphql_partial_success_is_an_error_and_messages_are_not_echoed(
    project, monkeypatch
):
    api = linear_api_client(project, monkeypatch)
    serve(
        monkeypatch,
        lambda url, payload: {
            "data": {"issue": linear_issue()},
            "errors": [{"message": "private-linear-token"}],
        },
    )
    with pytest.raises(tickets.TicketError) as error:
        api.get(api.resolve("ABC-123"))
    assert error.value.code == "api_error"
    assert "private-linear-token" not in str(error.value)


def test_jira_transition_is_a_plan_until_apply_and_rechecks_status(
    project, monkeypatch
):
    api = jira_api_client(
        project, monkeypatch, status_map={"in_progress": "In Progress"}
    )
    issue = jira_issue()

    def response(url, payload):
        if payload is not None:
            assert payload == {"transition": {"id": "31"}}
            issue["fields"]["status"] = {"id": "3", "name": "In Progress"}
            return {}
        if url.endswith("/transitions"):
            return {
                "transitions": [{"id": "31", "to": {"id": "3", "name": "In Progress"}}]
            }
        return copy.deepcopy(issue)

    calls = serve(monkeypatch, response)
    ticket = api.get(api.resolve("ABC-123"))
    assert api.transition(ticket, "in_progress")["status"] == "planned"
    assert all(payload is None for _, _, payload in calls)
    assert (
        api.transition(ticket, "in_progress", apply=True)["verified_status"]["id"]
        == "3"
    )
    assert sum(payload is not None for _, _, payload in calls) == 1
    assert (
        api.transition(api.get(api.resolve("ABC-123")), "in_progress", apply=True)[
            "status"
        ]
        == "unchanged"
    )
    assert sum(payload is not None for _, _, payload in calls) == 1


def test_acli_transition_works_without_api_credentials_and_uses_native_name(
    project, monkeypatch
):
    api = client(
        project,
        {
            "default_provider": "jira",
            "providers": {"jira": {"status_map": {"in_progress": "Doing"}}},
        },
    )
    monkeypatch.setattr(tickets.shutil, "which", lambda _: "/bin/acli")
    issue = jira_issue()
    writes = []

    def run(argv, **kwargs):
        if "transition" in argv:
            writes.append(argv)
            issue["fields"]["status"] = {"id": "3", "name": "Doing"}
        return subprocess.CompletedProcess(argv, 0, json.dumps(issue), "")

    monkeypatch.setattr(tickets.subprocess, "run", run)
    ticket = api.get(api.resolve("ABC-123"))
    assert api.transition(ticket, "in_progress", True)["status"] == "applied"
    assert writes == [
        [
            "acli",
            "jira",
            "workitem",
            "transition",
            "--key",
            "ABC-123",
            "--status",
            "Doing",
            "--yes",
        ]
    ]


def test_uncertain_write_outcome_is_not_retried_or_switched_to_another_transport(
    project, monkeypatch
):
    api = jira_api_client(project, monkeypatch)
    writes = []

    def response(url, payload):
        if payload is not None:
            writes.append(payload)
            raise tickets.TicketError("connection_failed", "timeout")
        if url.endswith("/transitions"):
            return {"transitions": [{"id": "31", "to": {"id": "3", "name": "Doing"}}]}
        return jira_issue()

    serve(monkeypatch, response)
    with pytest.raises(tickets.TicketError) as error:
        api.transition(api.get(api.resolve("ABC-123")), "Doing", True)
    assert error.value.code == "write_unconfirmed"
    assert len(writes) == 1


def test_duplicate_native_status_names_require_a_specific_status_id(
    project, monkeypatch
):
    api = jira_api_client(project, monkeypatch)
    serve(
        monkeypatch,
        lambda url, payload: (
            {
                "transitions": [
                    {"id": "31", "to": {"id": "3", "name": "Doing"}},
                    {"id": "41", "to": {"id": "4", "name": "Doing"}},
                ]
            }
            if url.endswith("/transitions")
            else jira_issue()
        ),
    )
    ticket = api.get(api.resolve("ABC-123"))
    with pytest.raises(tickets.TicketError) as error:
        api.transition(ticket, "Doing")
    assert error.value.code == "ambiguous_status"
    assert api.transition(ticket, "3")["native_action_id"] == "31"


def test_linear_transition_discovers_the_issue_teams_native_state(project, monkeypatch):
    api = linear_api_client(project, monkeypatch, status_map={"in_review": "Review"})
    issue = linear_issue()

    def response(url, payload):
        query = payload["query"]
        if "TicketStates" in query:
            assert payload["variables"] == {"id": "team-id"}
            return {
                "data": {
                    "team": {
                        "states": {
                            "nodes": [{"id": "review-id", "name": "Review"}],
                            "pageInfo": {"hasNextPage": False},
                        }
                    }
                }
            }
        if "MoveTicket" in query:
            assert payload["variables"] == {"id": "linear-id", "state": "review-id"}
            issue["state"] = {"id": "review-id", "name": "Review"}
            return {"data": {"issueUpdate": {"success": True}}}
        return {"data": {"issue": copy.deepcopy(issue)}}

    serve(monkeypatch, response)
    assert (
        api.transition(api.get(api.resolve("ABC-123")), "in_review", True)["status"]
        == "applied"
    )


def test_configured_cli_contract_uses_argument_arrays_without_shell_interpolation(
    project, monkeypatch
):
    cli = {
        "get": ["my-linear", "get", "{key}"],
        "statuses": ["my-linear", "statuses", "{id}"],
        "transition": ["my-linear", "move", "{id}", "{status}"],
    }
    api = client(
        project,
        {
            "default_provider": "linear",
            "providers": {"linear": {"workspace": "acme", "cli": cli}},
        },
    )
    monkeypatch.setattr(tickets.shutil, "which", lambda _: "/bin/my-linear")
    record = {
        "id": "native-id",
        "key": "ABC-123",
        "url": "https://linear.app/acme/issue/ABC-123/title",
        "title": "Title",
        "status": {"id": "todo", "name": "Todo"},
    }
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "statuses":
            value = [{"id": "doing", "name": "Doing"}]
        else:
            if argv[1] == "move":
                record["status"] = {"id": "doing", "name": "Doing"}
            value = record
        return subprocess.CompletedProcess(argv, 0, json.dumps(value), "")

    monkeypatch.setattr(tickets.subprocess, "run", run)
    ticket = api.get(api.resolve("ABC-123"))
    assert api.transition(ticket, "Doing", True)["status"] == "applied"
    assert ["my-linear", "move", "native-id", "doing"] in calls


@pytest.mark.parametrize("provider", ["jira", "linear"])
def test_pr_links_are_opt_in_and_use_provider_idempotency(
    project, monkeypatch, provider
):
    api = (
        jira_api_client(project, monkeypatch)
        if provider == "jira"
        else linear_api_client(project, monkeypatch)
    )
    writes = []

    def response(url, payload):
        if provider == "jira":
            if payload is not None:
                writes.append(payload)
                return {"id": "link-id"}
            return jira_issue()
        if "LinkPullRequest" in payload["query"]:
            writes.append(payload)
            return {
                "data": {
                    "attachmentCreate": {
                        "success": True,
                        "attachment": {
                            "id": "link-id",
                            "url": "https://github.com/acme/repo/pull/17",
                        },
                    }
                }
            }
        return {"data": {"issue": linear_issue()}}

    serve(monkeypatch, response)
    ticket = api.get(api.resolve("ABC-123"))
    pr = "https://github.com/acme/repo/pull/17"
    assert api.link_pr(ticket, pr)["status"] == "planned"
    assert not writes
    assert api.link_pr(ticket, pr, True)["status"] == "applied"
    assert api.link_pr(ticket, pr, True)["status"] == "applied"
    assert writes[0] == writes[1]
    if provider == "jira":
        assert writes[0]["globalId"].startswith("agentic-coding-workflow:pr:")
    else:
        assert writes[0]["variables"] == {"issue": "linear-id", "url": pr}


def test_doctor_reports_unchecked_api_auth_without_using_network(project, monkeypatch):
    api = linear_api_client(project, monkeypatch)
    report = api.doctor()
    assert report["providers"][1]["api"] == {
        "configured": True,
        "authentication": "not_checked",
        "write_permissions": "not_checked",
    }
    calls = serve(
        monkeypatch, lambda url, payload: {"data": {"viewer": {"id": "account-id"}}}
    )
    assert api.doctor(True)["providers"][1]["api"]["authentication"] == "authenticated"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status, code",
    [
        (401, "unauthenticated"),
        (403, "forbidden"),
        (404, "not_found"),
        (429, "rate_limited"),
        (302, "api_error"),
    ],
)
def test_http_failures_and_redirects_do_not_expose_response_bodies(
    monkeypatch, status, code
):
    class Opener:
        def open(self, request, **kwargs):
            raise urllib.error.HTTPError(
                request.full_url, status, "secret body", {}, None
            )

    monkeypatch.setattr(tickets.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(tickets.TicketError) as error:
        tickets.request_json(
            "https://example.atlassian.net/rest/api/3/myself",
            {"Authorization": "secret"},
            1,
        )
    assert error.value.code == code
    assert "secret" not in str(error.value)


def test_cli_entrypoint_outputs_actionable_json_without_tracebacks(project):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-dir",
            str(project),
            "--tracker",
            "jira",
            "get",
            "not-a-ticket",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "invalid_reference"
    assert not result.stderr


def test_scoped_jira_gateway_response_is_bound_to_the_configured_cloud_id(
    project, monkeypatch
):
    base = "https://api.atlassian.com/ex/jira/expected-cloud-id/rest/api/3"
    api = jira_api_client(project, monkeypatch, api={"base_url": base})
    issue = jira_issue()
    issue["self"] = base + "/issue/10001"
    serve(monkeypatch, lambda url, payload: issue)
    assert (
        api.get(api.resolve("ABC-123"))["url"]
        == "https://example.atlassian.net/browse/ABC-123"
    )
    issue["self"] = issue["self"].replace("expected-cloud-id", "other-cloud-id")
    with pytest.raises(tickets.TicketError):
        api.get(api.resolve("ABC-123"))


def test_successful_write_to_wrong_same_named_status_is_unconfirmed(
    project, monkeypatch
):
    api = jira_api_client(project, monkeypatch)
    issue = jira_issue()

    def response(url, payload):
        if payload is not None:
            issue["fields"]["status"] = {"id": "wrong-native-id", "name": "Doing"}
            return {}
        if url.endswith("/transitions"):
            return {"transitions": [{"id": "31", "to": {"id": "3", "name": "Doing"}}]}
        return copy.deepcopy(issue)

    serve(monkeypatch, response)
    with pytest.raises(tickets.TicketError) as error:
        api.transition(api.get(api.resolve("ABC-123")), "Doing", True)
    assert error.value.code == "write_unconfirmed"


def test_truncated_linear_states_cannot_drive_a_transition(project, monkeypatch):
    api = linear_api_client(project, monkeypatch)

    def response(url, payload):
        if "TicketStates" in payload["query"]:
            return {
                "data": {
                    "team": {
                        "states": {
                            "nodes": [{"id": "doing", "name": "Doing"}],
                            "pageInfo": {"hasNextPage": True},
                        }
                    }
                }
            }
        return {"data": {"issue": linear_issue()}}

    calls = serve(monkeypatch, response)
    with pytest.raises(tickets.TicketError) as error:
        api.transition(api.get(api.resolve("ABC-123")), "Doing", True)
    assert error.value.code == "incomplete_response"
    assert all("mutation" not in payload["query"] for _, _, payload in calls)


def test_api_request_uses_json_post_and_rejects_redirect_handlers(monkeypatch):
    captured = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return b'{"data":{"viewer":{"id":"account"}}}'

    class Opener:
        def open(self, request, timeout):
            captured.append(request)
            assert timeout == 5
            return Response()

    def opener(*handlers):
        assert any(isinstance(h, tickets.NoRedirect) for h in handlers)
        return Opener()

    monkeypatch.setattr(tickets.urllib.request, "build_opener", opener)
    payload = {"query": "query { viewer { id } }"}
    response = tickets.request_json(
        "https://api.linear.app/graphql", {"Authorization": "test-key"}, 5, payload
    )
    assert response["data"]["viewer"]["id"] == "account"
    assert captured[0].get_method() == "POST"
    assert json.loads(captured[0].data) == payload
    assert captured[0].get_header("Authorization") == "test-key"


def test_configured_cli_runs_end_to_end_with_spaced_paths(project):
    adapter = project / "adapter with spaces.py"
    adapter.write_text(
        "import json, sys\n"
        'print(json.dumps({"id":"native","key":sys.argv[1],'
        '"url":"https://linear.app/acme/issue/"+sys.argv[1]+"/title",'
        '"title":"Actual CLI read","status":{"id":"todo","name":"Todo"}}))\n'
    )
    client(
        project,
        {
            "default_provider": "linear",
            "providers": {
                "linear": {
                    "workspace": "acme",
                    "cli": {"get": [sys.executable, str(adapter), "{key}"]},
                }
            },
        },
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--project-dir", str(project), "get", "ABC-123"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["title"] == "Actual CLI read"


def test_configured_cli_transition_can_discover_states_through_api(
    project, monkeypatch
):
    cli = {
        "get": ["my-linear", "get", "{key}"],
        "transition": ["my-linear", "move", "{id}", "{status}"],
    }
    api = linear_api_client(project, monkeypatch, cli=cli)
    monkeypatch.setattr(tickets.shutil, "which", lambda _: "/bin/my-linear")
    record = {
        "id": "linear-id",
        "key": "ABC-123",
        "url": "https://linear.app/acme/issue/ABC-123/title",
        "title": "Title",
        "status": {"id": "todo", "name": "Todo"},
    }
    writes = []

    def run(argv, **kwargs):
        if argv[1] == "move":
            writes.append(argv)
            record["status"] = {"id": "doing", "name": "Doing"}
        return subprocess.CompletedProcess(argv, 0, json.dumps(record), "")

    def response(url, payload):
        if "TicketStates" in payload["query"]:
            return {
                "data": {
                    "team": {
                        "states": {
                            "nodes": [{"id": "doing", "name": "Doing"}],
                            "pageInfo": {"hasNextPage": False},
                        }
                    }
                }
            }
        return {"data": {"issue": linear_issue()}}

    monkeypatch.setattr(tickets.subprocess, "run", run)
    serve(monkeypatch, response)
    ticket = api.get(api.resolve("ABC-123"))
    assert api.transition(ticket, "Doing", True)["status"] == "applied"
    assert writes == [["my-linear", "move", "linear-id", "doing"]]
