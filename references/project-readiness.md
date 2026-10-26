# Project readiness for verification and review

The consuming project owns its environment, commands, and required checks.
Installing this plugin does not select a dependency manager, linter, type
checker, test runner, or deployment policy.

## Record the operating contract

Keep a short contract in existing project guidance (`CLAUDE.md`, `AGENTS.md`,
README, or linked development docs). Point to canonical sources instead of
copying their contents:

- Supported runtimes and the existing reproducible setup command/lockfiles.
- Required local services, fixtures, test configuration, and readiness checks;
  describe required credentials by name, without storing their values.
- How to run relevant product flows, including API or browser checks when
  needed, and how to find their logs.
- Architecture examples, component owners, review expectations, and sensitive
  paths or compatibility requirements.
- For concurrent worktrees, service/port isolation and how environment inputs
  are provided. Git worktrees alone do not isolate databases or listening ports.

Provisioning and enforced execution isolation are separate work recorded in
[the setup and unattended execution plan](../.claude/plans/reproducible-setup-and-unattended-execution.md).

## Select existing verification commands

Save the project's actual CI/task commands in `.claude/project-commands.json`.
The supported keys remain `build`, `test`, `lint`, `format`, and `run`. The Stop
hook runs configured **lint and test** commands; include required check-only
formatting, typing, and other static checks in the project's lint task.
Required build/integration checks must also be run for changes that need them
and before a merge when project policy requires them.

For example, a Go project already using these checks might select:

```json
{"lint": "go vet ./...", "test": "go test ./..."}
```

A TypeScript repository whose existing package manager and scripts are pnpm,
lint, typecheck, and test:ci might select:

```json
{"lint": "pnpm run lint && pnpm run typecheck", "test": "pnpm run test:ci"}
```

These are examples, not defaults to install. Retain Python's existing tooling;
the [Python profile](../profiles/python/uv-ruff-basedpyright/README.md) is optional.
For mixed projects, use project-owned aggregate tasks or explicit commands that
cover every affected component. The configuration works even without a
recognized language marker. Use the project's package manager and lockfile;
check commands must not fix files, change dependencies, or install tools.

## Inspect configuration without running checks

From the consuming project, with `CLAUDE_PLUGIN_ROOT` set to the plugin checkout:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project-commands.py" readiness "$PWD"
```

This prints JSON and never executes, installs, or writes anything. It reports
root-level markers for Go (`go.mod`/`go.work`), Python, TypeScript/JavaScript,
and Elixir; nested monorepos should supply aggregate commands at their root.
It inspects command configuration only. `verification: "not_run"` means it has
not established that tools, dependencies, services, or product flows work.

| Status | Meaning | Exit |
| --- | --- | --- |
| `configured` | Each lint/test action is configured or explicitly disabled; at least one command is selected | 0 |
| `disabled` | Both actions were explicitly disabled; no checks will run | 0 |
| `unconfigured` | A recognized project or explicit config has missing lint/test actions | 1 |
| `invalid` | Project/configuration could not be read or validated | 2 |
| `legacy_elixir` | Elixir-only project without config uses the existing format/test runner | 0 |
| `not_applicable` | No supported root marker or command configuration was found | 0 |

An omitted action is unknown; `null` or `""` is an explicit disable. Do not
disable an unknown check to silence an incomplete result. Existing project
policy decides whether a disable is appropriate.

The existing command reader also accepts `get <project> <action> --required`.
Stop and Ralph use this configuration contract; the generator leaves unknown
Go/Python/Node/mixed tasks missing and preserves explicit overrides. Legacy
defaults remain available for Elixir-only roots. The inspector does not parse
shell commands to infer whether they cover every component; owners select
and review aggregate scope.

## Stop verification

Configured commands run for any stack, including Go, Python, TypeScript, and
mixed repositories. The hook preserves shell quoting and pipeline failures,
runs no formatting fixes, and binds outcomes to the revision/working inputs.
Configuration overrides also apply to Elixir; its legacy runner is retained
only for an Elixir-only project without a command file.

Missing checks produce `incomplete` and an explicit block instead of success.
Configured independent checks still run. Both actions explicitly disabled
produce a `disabled` record, never `passed`. Invalid configuration blocks.
Correction attempts retain the existing three-attempt bound; exhaustion records
`blocked` and hands off to the user. Missing services remain incomplete.

Local records and hooks provide feedback. Required CI checks, repository
protections, code owners, and human approval establish the team's merge rules.
