---
name: verify-agentic-coding-workflow
description: Exercise this plugin's public verification command reader, Stop hook, and shared delivery gate with retained local evidence.
allowed-tools:
  - Read
  - Bash
---

# Verify plugin delivery behavior

From this repository's root (`${CLAUDE_PROJECT_DIR}`), run `maak verify` in the
locked development environment. If setup is missing, report verification as
unavailable; `maak setup` is the separate environment preparation task.

The command launches the registered Stop check and public command-reader CLI in
a disposable Git project with isolated fixture data. It needs Git, Bash, jq,
and the project environment; no server, credentials, or model calls are needed.
Every subprocess has a timeout. The driver removes its temporary project on
success or failure and preserves evidence in `.claude/proofs/delivery/run-*/`.

| Path | Observable success criterion |
| --- | --- |
| Command reader | Reports configured `verify` without executing it or claiming verification |
| Stop and shared delivery gate | Both reject a failing product check and accept corrected behavior |
| Correction turn | Success is reused for exactly the same source, without another product-check invocation |
| Source change | A later regression invalidates cached success, reruns the check, and blocks completion |
| Cleanup and evidence | Scratch project is removed; commands, raw outputs/exits, source records, and summary remain |

Inspect the `summary.json` path printed by the command and the per-command
`.result.json`, stdout/stderr, and Stop records beside it. A pass requires all
criteria, unchanged plugin source before/after, and successful cleanup. Report
the checked source, criteria, result, and evidence path. A nonzero exit or missing
evidence remains incomplete.

This exercise proves local hook/CLI behavior. Native Claude session interaction
and external integrations require their own execution evidence. See
[validation and maintenance](../../../README.md#validation-and-maintenance)
for native testing; those checks are separate from this proved local procedure.
