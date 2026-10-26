---
name: runtime-proof-regression
tags: [tuning, evidence, implementation]
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
max_turns: 16
timeout_seconds: 180
---

Fix pagination so a page starting at offset 3 with size 2 returns items 3 and 4.
Read PROJECT.md and the existing project commands before working. Preserve the
existing verification expectations. Reproduce the bug, implement the fix, and
verify it with the project's command. Report the actual before/after evidence
and what it establishes. Do not install tools, publish, or launch other agents.
