# Repository development

Read [CLAUDE.md](CLAUDE.md) for the plugin architecture and development policy.

Install pinned Maak with `bash scripts/install-maak.sh` and add its installation
prefix's `bin` directory to `PATH`; see README for prerequisites.
Run `maak setup` to create or synchronize the locked development environment.
Run `maak check` before completing a change; `maak lint`, `maak test`, and
`maak verify` run its individual checks. CI and `.claude/project-commands.json`
use these same tasks.
Use the project environment for Python tools rather than the global interpreter.
See [README.md](README.md#validation-and-maintenance) for prerequisites, focused
tests, dependency updates, and optional native plugin validation.
The local product-verification runbook is
[verify-agentic-coding-workflow](.claude/skills/verify-agentic-coding-workflow/SKILL.md).
