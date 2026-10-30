---
name: setup-python-rules
description: "Configure project-specific Python guidance while preserving its selected toolchain."
metadata:
  workflow-source: "commands/setup-python-rules.md"
---


# Setup Python Rules

Installs project-specific judgment guidance in `.claude/rules/python.md`. The default keeps the project's existing tools and library versions. Formatting, lint, and typing policy belongs in actual tool configuration; installing this plugin enables no Python toolchain gate or regex style hook.

## Input

$ARGUMENTS — Optional flags:

- `--preview` — show proposed rules and any profile/configuration changes without writing files or installing dependencies
- `--force` — replace the existing rules file without asking; does not authorize replacing tool configuration or migrating tooling
- `--profile uv-ruff-basedpyright` — explicitly select the optional uv, Ruff, basedpyright, and pytest profile
- Empty — install guidance adapted to the current project

Reject unknown profiles before making changes.

## Instructions

### Phase 1: Inspect the Project

Read existing `.claude/rules/python.md`, project instructions, `pyproject.toml`, `setup.cfg`, dependency/lock files, CI, task runners, and `.claude/project-commands.json` where present. Identify the supported Python version, actual tooling, source/test scope, exclusions, and library versions. An installed executable or `pyproject.toml` alone does not select a toolchain.

If rules already exist and `--force` is absent, offer merge, replace, or cancel, unless the user already chose. In preview mode, show the proposed merge without prompting to install. Respect pip, Poetry, Black, mypy, unittest, Pydantic v1 compatibility, and other configured choices. Ask only when missing information affects the proposed setup.

### Phase 2: Prepare Guidance and Tool Configuration

Read `${CLAUDE_PLUGIN_ROOT}/.claude/rules/python.md` as a judgment-oriented starting point. Keep its `paths: ["**/*.py"]` scope and adapt the guidance to the project. Include library-specific guidance only when that library and version apply. Do not copy mandatory tool preferences, mechanical lint rules, or API migration requirements into agent instructions.

Without `--profile`, preserve the current toolchain. When existing CI/task commands clearly identify the project's checks, propose corresponding missing `lint`, `test`, and `format` entries in `.claude/project-commands.json`. Preserve existing entries, including intentional null/empty disables. `lint` should run the project's check-only formatting, lint, and typing requirements; `test` runs its selected framework. Do not invent commands for unconfigured tools; report missing required checks. Keep paths and exclusions in the tools' own configuration. Custom hooks, if requested, must match the relevant tool and files and invoke configured checks rather than infer library semantics from regexes.

With `--profile uv-ruff-basedpyright`, read the files under `${CLAUDE_PLUGIN_ROOT}/profiles/python/uv-ruff-basedpyright/`. Prepare concrete merges into the project's actual `pyproject.toml` and `.claude/project-commands.json`. Preserve unrelated tables, existing overrides/disables, source/test roots, and exclusions; adapt the Python target. Do not duplicate TOML tables. Identify development dependency changes and environment setup. If the project already uses a conflicting stack, present the concrete migration for approval unless that migration was already authorized; the flag alone does not authorize discarding existing policy.

### Phase 3: Preview or Install

For `--preview`, show the adapted guidance, proposed configuration/dependency changes, and unresolved decisions, then stop without mutations.

Otherwise, create `.claude/rules/` as needed and write the requested guidance. Apply authorized configuration merges. A routine setup request authorizes installing the adapted rules; do not add a redundant approval round. Obtain approval only for an unresolved overwrite, tooling migration, or other material scope decision. Do not install or replace dependencies merely to install judgment guidance.

Report the rules path, selected tools, changed configuration files, commands available for verification, and any checks that remain unconfigured. Validate modified TOML/JSON and run available, relevant checks. Never report unrun or unconfigured checks as passed.

## Error Handling

- **No Python files:** Explain the mismatch; install only if Python setup is still intended.
- **Invalid existing tool or command configuration:** Report the error and preserve the file for correction.
- **Ambiguous runner or conflicting policy:** Prepare the supported options and resolve the material choice before changing configuration.
- **Missing tools:** Report the environment setup needed; do not switch to the optional stack automatically.

## Example Usage

```text
/agentic-coding-workflow:setup-python-rules
/agentic-coding-workflow:setup-python-rules --preview
/agentic-coding-workflow:setup-python-rules --profile uv-ruff-basedpyright --preview
/agentic-coding-workflow:setup-python-rules --profile uv-ruff-basedpyright
/agentic-coding-workflow:setup-python-rules --force
```
