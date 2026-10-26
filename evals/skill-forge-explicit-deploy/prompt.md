---
name: skill-forge-explicit-deploy
tags: [holdout, skills]
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
max_turns: 12
timeout_seconds: 180
---

Draft a Claude Code skill at skills/deploy-preview/SKILL.md for publishing a
preview build. I want to run it myself from the slash menu; Claude must not
start it automatically. When invoked, it should accept the target environment
and build identifier, use the consuming project's documented deployment
command, and verify the resulting preview URL. If the target or project
command is unresolved, clarify that before publishing. Don't assume a cloud
provider or add broad prompt-free shell approval. Only write the skill now;
don't deploy anything, run shell commands, create infrastructure, launch
agents, or make paid evaluation calls.
