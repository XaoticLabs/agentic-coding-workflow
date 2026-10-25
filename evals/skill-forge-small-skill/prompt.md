---
name: skill-forge-small-skill
tags: [skills]
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
max_turns: 12
timeout_seconds: 180
---

Create a reusable Claude Code skill at skills/standup-summary/SKILL.md. It should
turn pasted standup notes into three bullets: completed work, next steps, and
blockers. Don't invent missing facts; say when a category has no information.
Use it for requests to summarize standup notes, not for ordinary prose editing.
This only needs instructions. Keep it self-contained, without extra scripts,
reference files, research, agent launches, or paid evaluation runs.
