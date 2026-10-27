---
name: verify-project
description: Exercise real project behavior with reproducible evidence, or create a project-local verification runbook when requested. Use for runtime QA of a CLI, API, web app, worker, or library.
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Write
effort: medium
---

# Verify project behavior

Use the current project's actual runtime and test configuration. Read
[verification evidence](../../references/verification-evidence.md) for proof
requirements and [graph engineering](../../references/graph-engineering.md) when
designing a separate verification node.

1. Identify the requested criterion and surface from code, existing tests, CI,
   and documentation. Reuse an existing verification runbook or configured
   `verify` command. Ask only for a material target/criterion that cannot be
   inferred. Do not assume a browser, Bun, pytest, or a provider.
2. Establish the launch, readiness, drive, observe, and cleanup procedure. Reuse
   the project's Playwright/HTTP/PTY/library harness. Allocate owned ports/data
   when parallel execution would otherwise share mutable state. Inspect what a
   dry-run actually does before treating it as side-effect-free.
3. Snapshot source, run the agreed user path, assert its observable outcome and
   side effects, and retain commands, raw output/exits, artifacts, and target
   identity under `.claude/proofs/`. Snapshot again. Source changes invalidate
   fixed-source evidence. Missing setup is `unavailable`, not pass.
4. Clean up only resources created by the exercise and verify the evidence still
   exists. Report criterion-level results and remaining gaps. Do not repair the
   product during an independently requested verification pass.

When asked to make verification reusable, save a project-local
`.claude/skills/verify-<project>/SKILL.md` with working frontmatter and only the
tested launch/readiness/drive/evidence/cleanup instructions. Include a small
feature map of the actual requested paths and their observable success criteria.
Run one complete journey from those saved instructions before calling the
runbook usable. A generated but unexecuted runbook remains a draft.

Where the project wants a command-based gate, put its approved check-only
procedure in `.claude/project-commands.json` as `verify`. Relay runs it alongside
lint/test. The ordinary Stop hook uses the project's lint/test configuration;
include required runtime checks there if they must gate ordinary sessions too.

Browser tooling, external credentials, network targets, and containment must be
available in the selected environment. Report missing capabilities directly;
do not install an unrelated workflow pack or claim a static read was live QA.
