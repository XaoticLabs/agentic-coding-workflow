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

Use [private execution environments](execution-environments.md) for explicit
setup, service readiness, resource limits, and isolated source. Trusted policy
enforcement and production credential brokering remain separate work.

## Select existing verification commands

Save the project's actual CI/task commands in `.claude/project-commands.json`.
The core keys remain `build`, `test`, `lint`, `format`, and `run`. Optional
`install` is used only by explicit environment setup. `health`, `logs`,
`deploy_status`, and `flag_status` support [lifecycle observations](lifecycle-observation.md).
`verify` adds an optional project-owned product gate to Stop, Relay, and the
shared delivery gate used for final integration checks. Once configured, it must
pass along with lint/test. `quick_check` opts into a short advisory check after
edits; it never populates final verification evidence.
Initialization retains its five core arguments and preserves extra keys. The Stop
hook runs configured **lint, test, and verify** commands; include required check-only
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

For product verification, reuse a tested project-local runbook and existing
browser/HTTP/CLI harness. Select a short journey with observable outcomes and
isolated data; retain commands, exits, logs, and artifacts in `.claude/proofs/`.
Return nonzero on failed or unavailable required checks. Configure its task as
`verify` and run that same task in required CI. Keep it separate from aggregate
`test` tasks that already run it, to avoid duplicate execution. The
[`verify-project` skill](../skills/verify-project/SKILL.md) can exercise the journey
and save a runbook with launch, readiness, drive, evidence, and cleanup steps.

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
| `configured` | Each lint/test action is configured or explicitly disabled; at least one lint/test/verify command is selected | 0 |
| `disabled` | Lint/test and any configured verify action are explicitly disabled; no checks will run | 0 |
| `unconfigured` | A recognized project or explicit config has missing lint/test actions | 1 |
| `invalid` | Project/configuration could not be read or validated | 2 |
| `legacy_elixir` | Elixir-only project without config uses the existing format/test runner | 0 |
| `not_applicable` | No supported root marker or command configuration was found | 0 |

An omitted lint/test action is unknown; an omitted optional `verify` adds no
check and is absent from the report's `checks`. A configured `verify` appears in
`checks` and counts toward `configured` even when lint/test are disabled.
`null` or `""` is an explicit disable. Do not
disable an unknown check to silence an incomplete result. Existing project
policy decides whether a disable is appropriate.

The existing command reader also accepts `get <project> <action> --required`.
Stop and Relay use this configuration contract; the generator leaves unknown
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

Missing lint/test checks produce `incomplete` and an explicit block instead of
success. Configured independent checks, including `verify`, still run. All
selected actions explicitly disabled produce a `disabled` record, never
`passed`. Invalid configuration blocks.
Correction attempts retain the existing three-attempt bound; exhaustion records
`blocked` and hands off to the user. Missing services remain incomplete.

Local records and hooks provide feedback. Required CI checks, repository
protections, code owners, and human approval establish the team's merge rules.
