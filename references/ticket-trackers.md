# Jira and Linear through CLI/API tools

All ticket-aware commands use `scripts/tickets.py`. Provider selection and
connection selection are separate. No MCP connector, dependency installation,
login, or authentication switching is performed. Python 3.11+ and its standard
library are sufficient; install/authenticate your preferred CLI separately.

## Configure a consuming repository

Create `.claude/ticket-tracker.json` in the repository you are working on, not
in the plugin checkout. Configuration is optional when an unambiguous CLI/API
connection is available. A bare key like `ABC-123` does not identify its tracker.

```json
{
  "version": 1,
  "default_provider": "jira",
  "timeout": 30,
  "providers": {
    "jira": {
      "site": "https://example.atlassian.net",
      "transport": "auto",
      "status_map": {
        "in_progress": "In Progress",
        "in_review": "Code Review",
        "done": "Done"
      },
      "acceptance_fields": ["customfield_10001"]
    },
    "linear": {
      "workspace": "acme",
      "transport": "auto",
      "status_map": {
        "in_progress": "Started",
        "in_review": "In Review",
        "done": "Done"
      }
    }
  }
}
```

Use your actual site, workspace URL slug, statuses, and field IDs. Omit unused
providers/fields. There is no universal meaning or spelling for native workflow
statuses. Share nonsecret configuration according to repository conventions;
this plugin repository ignores runtime `.claude/` files by default. Carry the
selected configuration into new worktrees, preserving existing destination
files. CLI executables and credentials belong to the execution environment.

Selection order is an explicit `--tracker`, ticket URL, project default, then a
single available provider. An explicit tracker conflicting with a URL fails.
A configured site/workspace must match the URL and returned ticket. With two
possible providers and no selection, the resolver reports `ambiguous_provider`.
Availability is not proof of authentication: an actual read must succeed.

`auto` chooses an installed, supported CLI operation first and falls back to a
configured API only when that operation/executable is unavailable. `cli` and
`api` select that transport exclusively. A failing installed CLI does **not**
fall back: correct authentication, access, or the CLI interface explicitly.
When an operation switches transport, the API/CLI must return the same site or
workspace, key, and native ID before the operation proceeds.

## Connections and credentials

| Operation | Built-in Jira ACLI | Jira Cloud API | Linear API | Configured CLI |
| --- | --- | --- | --- | --- |
| Get ticket | Yes | Yes | Yes | When configured |
| Discover workflow states | Unavailable | Reachable transitions | Issue team's states | When configured |
| Transition | Native status name | Discovered target status | Discovered target state | When configured |
| Link PR | Unavailable | Remote issue link | URL attachment | When configured |

The built-in ACLI adapter uses `acli jira workitem view KEY --json --fields *all`
and `acli jira workitem transition --key KEY --status NAME --yes`. The returned
`self` URL verifies the active Jira site; the resolver never runs `auth switch`.
For ACLI-only transitions, an explicit native name or configured mapping is
validated by Jira when the command runs, then re-read to verify the result.
It does not claim to have discovered statuses. Use API state discovery when
you need to choose among statuses or use native IDs. No other Jira/Linear CLI
binary is guessed from its executable name.

Jira API defaults to `JIRA_EMAIL` and `JIRA_API_TOKEN` using Basic auth. The
Jira `site` must be explicitly configured before any API credential is sent;
a supplied ticket URL does not establish a credential destination. For scoped
API tokens, set `api.base_url` to your configured Atlassian API gateway path,
for example `https://api.atlassian.com/ex/jira/CLOUD_ID/rest/api/3`, retaining
the actual browser `site` for ticket identity. OAuth access tokens can use
`"api": {"auth": "bearer", "token_env": "JIRA_ACCESS_TOKEN"}`.

Linear API defaults to `LINEAR_API_KEY`, sent as the personal-key Authorization
header to `https://api.linear.app/graphql`. For OAuth use
`"api": {"auth": "bearer", "token_env": "LINEAR_ACCESS_TOKEN"}`. Both API
adapters allow `token_env`; Jira additionally allows `email_env`. Store only
environment variable **names**, never credential values, in configuration.
The resolver does not read `.env` files or extract credentials from CLI stores.
Provide the environment using your existing shell/secret tooling.

CLI authentication and API authentication are separate. HTTPS is required;
authenticated HTTP redirects are rejected. Reads and writes have per-operation
timeouts; writes are never automatically retried. API errors and CLI failures
are reported without copying response bodies, credentials, or raw CLI stderr.
The Jira API adapter targets Cloud REST v3; Data Center and other CLI schemas
need an explicitly configured compatible adapter.

## Command interface

Global options precede the operation. Every successful command returns JSON;
errors return JSON with `status`, `code`, and `error`, exiting with status 2.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tickets.py" --project-dir "$PWD" doctor
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tickets.py" --project-dir "$PWD" doctor --check
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tickets.py" --project-dir "$PWD" --tracker jira get ABC-123
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tickets.py" --project-dir "$PWD" statuses "https://linear.app/acme/issue/ABC-123/title"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tickets.py" --project-dir "$PWD" transition "https://example.atlassian.net/browse/ABC-123" in_progress
```

`doctor` locates supported executables, probes configured version commands, and
reports per-operation availability. Authentication remains `not_checked` until
`doctor --check` or a real read. `--check` performs read-only CLI/API probes; it
does not establish write permissions. Read the report's individual fields; exit
0 means inspection completed, not that every connection is authenticated.

`get` returns schema version, provider, native ID, key, canonical URL, scope,
title, description, status, assignee, comments, links, acceptance criteria,
transport, timestamp, and limitations. Jira's Atlassian Document Format is
converted to text; Linear Markdown is retained. Jira configured acceptance fields
are included; otherwise criteria remain in the description/comments. An empty
structured list does not mean the ticket has no acceptance criteria.

Context is bounded: Jira returns the comments in the issue response (at most
50), Linear reads the first 50 comments and the parent link. Partial comments
are marked `comments_truncated`. This is not an exhaustive dependency or
attachment crawler. Retrieve relevant missing context through the same account
before claiming full requirements coverage. Linear status discovery rejects
a truncated state list rather than choosing from incomplete results.

`transition REF TARGET` and `link-pr REF PR_URL` prepare JSON proposals and do
not write. Append `--apply` only for an authorized write. A transition already
at the requested target is unchanged. Jira API selection distinguishes target
status IDs from transition IDs; duplicate names require a specific target ID.
After a write, status transitions are re-read and verified. An unconfirmed write
reports `write_unconfirmed`: check current remote state before a retry.

API PR links are idempotent: Jira uses a stable remote-link global ID and Linear
uses the issue/URL attachment identity. Custom CLI link commands must preserve
that property. Linking does not post a comment, move a ticket, or merge a PR.

## Configuring another CLI interface

The `cli` object replaces the built-in CLI definition for that provider.
Declare only operations your CLI actually supports. Each command is an argv
array, executed directly without a shell. No pipes, shell interpolation, or
implicit installation. This example is an **adapter contract**, not a claim
that a particular Linear distribution uses these commands:

```json
{
  "default_provider": "linear",
  "providers": {
    "linear": {
      "workspace": "acme",
      "cli": {
        "version": ["my-linear-adapter", "version"],
        "doctor": ["my-linear-adapter", "auth-status"],
        "get": ["my-linear-adapter", "get", "{key}"],
        "statuses": ["my-linear-adapter", "statuses", "{id}"],
        "transition": ["my-linear-adapter", "transition", "{id}", "{status}"],
        "link-pr": ["my-linear-adapter", "link-pr", "{id}", "{url}"]
      }
    }
  }
}
```

Available placeholders are `{key}`, `{id}`, `{url}`, `{status}`, `{site}`, and
`{workspace}`. They must occupy an entire argument. `get` knows only the key
and configured/URL site or workspace. Other operations know the fetched native
ID; `{url}` is the PR URL for `link-pr`. `{status}` is the discovered native
status/state ID for custom CLI transitions. `doctor`/`version` take no ticket
placeholders. Configuration is executable project tooling: review it as you
would project task commands.

`get` must return the normalized object (at least `id`, `key`, `url`, `title`,
and `status: {"id": "...", "name": "..."}`); other contextual fields are
optional. `statuses` returns an array of `{id, name}` objects; a Jira-style
adapter may include `status_id` when the action ID differs from the status ID.
Other operations return exit 0 only on success. Transitions are verified with
another `get`. Authentication and version checks also use their exit status.

## Sources

- [ACLI view](https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-view/), [transition](https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-transition/), and [auth status](https://developer.atlassian.com/cloud/acli/reference/commands/jira-auth-status/).
- [Jira issue REST operations](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/) and [remote links](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-remote-links/).
- [Linear GraphQL/authentication](https://linear.app/developers/graphql) and [idempotent URL attachments](https://linear.app/developers/attachments).
